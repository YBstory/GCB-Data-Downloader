import os
import sys
import time
import json
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def format_speed(speed_bytes):
    """格式化下载速度"""
    if speed_bytes < 1024:
        return f"{speed_bytes:.0f} B/s"
    elif speed_bytes < 1024 * 1024:
        return f"{speed_bytes / 1024:.1f} KB/s"
    else:
        return f"{speed_bytes / (1024 * 1024):.1f} MB/s"

class GCBDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("GCB 数据下载器")
        self.root.geometry("1200x850")
        
        self.driver = None
        self.all_files = {}  # {url: {'path': relative_path, 'size': size_str}}
        self.downloaded_files = set()  # 已下载完成的文件路径
        self.failed_files = set()  # 下载失败的文件路径
        self.download_queue = []
        self.is_scanning = False
        self.is_downloading = False
        self.stop_download = False
        self.cache_file = "gcb_file_cache.json"  # 缓存文件名
        self.downloaded_record_file = "gcb_downloaded_record.json"  # 已下载记录文件
        self.failed_record_file = "gcb_failed_record.json"  # 下载失败记录文件
        self.show_all_files = True  # 显示全部/仅未下载
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 1  # 重试间隔（秒）
        
        self.setup_ui()
        # 先加载记录（不刷新UI），再加载缓存，最后统一刷新一次
        self.load_downloaded_record(refresh_ui=False)
        self.load_failed_record(refresh_ui=False)
        self.load_cache()  # load_cache会构建树，已包含状态信息
        
    def setup_ui(self):
        """设置界面"""
        # 顶部控制区
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=X)
        
        ttk.Label(top_frame, text="网址:").pack(side=LEFT)
        self.url_entry = ttk.Entry(top_frame, width=50)
        self.url_entry.insert(0, "https://mdosullivan.github.io/GCB/")
        self.url_entry.pack(side=LEFT, padx=5)
        
        self.scan_btn = ttk.Button(top_frame, text="扫描文件", command=self.start_scan)
        self.scan_btn.pack(side=LEFT, padx=5)
        
        self.save_cache_btn = ttk.Button(top_frame, text="保存缓存", command=self.save_cache)
        self.save_cache_btn.pack(side=LEFT, padx=2)
        
        self.load_cache_btn = ttk.Button(top_frame, text="加载缓存", command=self.load_cache)
        self.load_cache_btn.pack(side=LEFT, padx=2)
        
        ttk.Label(top_frame, text="保存目录:").pack(side=LEFT, padx=(20,0))
        self.save_dir_entry = ttk.Entry(top_frame, width=30)
        self.save_dir_entry.insert(0, "GCB_Data")
        self.save_dir_entry.pack(side=LEFT, padx=5)
        
        ttk.Button(top_frame, text="浏览", command=self.browse_save_dir).pack(side=LEFT)
        
        # 筛选区
        filter_frame = ttk.Frame(self.root, padding="10")
        filter_frame.pack(fill=X)
        
        ttk.Label(filter_frame, text="筛选:").pack(side=LEFT)
        self.filter_entry = ttk.Entry(filter_frame, width=30)
        self.filter_entry.pack(side=LEFT, padx=5)
        self.filter_entry.bind('<KeyRelease>', self.apply_filter)
        
        ttk.Label(filter_frame, text="文件类型:").pack(side=LEFT, padx=(20,0))
        self.ext_var = StringVar(value="全部")
        self.ext_combo = ttk.Combobox(filter_frame, textvariable=self.ext_var, width=10, state="readonly")
        self.ext_combo['values'] = ['全部', '.nc', '.xlsx', '.xls', '.csv', '.zip', '.pdf']
        self.ext_combo.pack(side=LEFT, padx=5)
        self.ext_combo.bind('<<ComboboxSelected>>', self.apply_filter)
        
        ttk.Separator(filter_frame, orient=VERTICAL).pack(side=LEFT, padx=10, fill=Y)
        
        self.show_all_var = StringVar(value="显示全部")
        self.toggle_view_btn = ttk.Button(filter_frame, textvariable=self.show_all_var, command=self.toggle_file_view, width=12)
        self.toggle_view_btn.pack(side=LEFT, padx=5)
        
        self.downloaded_count_label = ttk.Label(filter_frame, text="已下载: 0")
        self.downloaded_count_label.pack(side=LEFT, padx=10)
        
        self.failed_count_label = ttk.Label(filter_frame, text="失败: 0", foreground='#CC0000')
        self.failed_count_label.pack(side=LEFT, padx=5)
        
        # 主区域 - 分为左右两部分
        main_paned = ttk.PanedWindow(self.root, orient=HORIZONTAL)
        main_paned.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 左侧 - 文件树
        left_frame = ttk.LabelFrame(main_paned, text="文件列表（勾选要下载的文件）", padding="5")
        main_paned.add(left_frame, weight=2)
        
        # 文件树操作按钮
        tree_btn_frame = ttk.Frame(left_frame)
        tree_btn_frame.pack(fill=X, pady=(0,5))
        
        ttk.Button(tree_btn_frame, text="全选", command=self.select_all).pack(side=LEFT, padx=2)
        ttk.Button(tree_btn_frame, text="取消全选", command=self.deselect_all).pack(side=LEFT, padx=2)
        ttk.Button(tree_btn_frame, text="反选", command=self.invert_selection).pack(side=LEFT, padx=2)
        ttk.Button(tree_btn_frame, text="排除已下载", command=self.exclude_downloaded).pack(side=LEFT, padx=2)
        ttk.Separator(tree_btn_frame, orient=VERTICAL).pack(side=LEFT, padx=5, fill=Y)
        ttk.Button(tree_btn_frame, text="选中文件夹", command=self.select_folder).pack(side=LEFT, padx=2)
        ttk.Button(tree_btn_frame, text="取消选中文件夹", command=self.deselect_folder).pack(side=LEFT, padx=2)
        
        self.file_count_label = ttk.Label(tree_btn_frame, text="共 0 个文件")
        self.file_count_label.pack(side=RIGHT)
        
        # 创建带滚动条的树形视图
        tree_container = ttk.Frame(left_frame)
        tree_container.pack(fill=BOTH, expand=True)
        
        self.tree = ttk.Treeview(tree_container, columns=('size', 'selected'), show='tree headings')
        self.tree.heading('#0', text='文件路径')
        self.tree.heading('size', text='大小')
        self.tree.heading('selected', text='选中')
        self.tree.column('#0', width=400)
        self.tree.column('size', width=80, anchor=CENTER)
        self.tree.column('selected', width=50, anchor=CENTER)
        
        tree_scroll_y = ttk.Scrollbar(tree_container, orient=VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_container, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        tree_scroll_y.grid(row=0, column=1, sticky='ns')
        tree_scroll_x.grid(row=1, column=0, sticky='ew')
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        
        # 配置标签样式 - 已下载文件显示蓝色，失败显示红色
        self.tree.tag_configure('downloaded', foreground='#0066CC')
        self.tree.tag_configure('failed', foreground='#CC0000')
        self.tree.tag_configure('file', foreground='black')
        
        self.tree.bind('<Double-1>', self.toggle_item)
        self.tree.bind('<space>', self.toggle_item)
        self.tree.bind('<Button-3>', self.show_context_menu)  # 右键菜单
        
        # 创建右键菜单
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="选中此文件夹下所有文件", command=self.select_folder)
        self.context_menu.add_command(label="取消选中此文件夹下所有文件", command=self.deselect_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="展开所有", command=self.expand_all)
        self.context_menu.add_command(label="折叠所有", command=self.collapse_all)
        
        # 右侧 - 日志和下载控制
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)
        
        # 下载控制
        download_frame = ttk.LabelFrame(right_frame, text="下载控制", padding="5")
        download_frame.pack(fill=X, pady=(0,5))
        
        # 第一行：选择数量和并行数
        ctrl_row1 = ttk.Frame(download_frame)
        ctrl_row1.pack(fill=X, pady=2)
        
        self.selected_count_label = ttk.Label(ctrl_row1, text="已选择: 0 个文件")
        self.selected_count_label.pack(side=LEFT)
        
        ttk.Label(ctrl_row1, text="并行下载:").pack(side=LEFT, padx=(20, 5))
        self.parallel_var = StringVar(value="1")
        self.parallel_combo = ttk.Combobox(ctrl_row1, textvariable=self.parallel_var, width=3, state="readonly")
        self.parallel_combo['values'] = ['1', '2', '3', '4', '5']
        self.parallel_combo.pack(side=LEFT)
        self.parallel_combo.bind('<<ComboboxSelected>>', self.on_parallel_change)
        
        # 第二行：按钮
        btn_frame = ttk.Frame(download_frame)
        btn_frame.pack(fill=X, pady=5)
        
        self.download_btn = ttk.Button(btn_frame, text="开始下载", command=self.start_download)
        self.download_btn.pack(side=LEFT, padx=2)
        
        self.stop_btn = ttk.Button(btn_frame, text="停止下载", command=self.stop_download_func, state=DISABLED)
        self.stop_btn.pack(side=LEFT, padx=2)
        
        # 总体进度
        ttk.Label(download_frame, text="总体进度:").pack(anchor=W, pady=(5,0))
        self.progress_var = DoubleVar()
        self.progress_bar = ttk.Progressbar(download_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=X, pady=2)
        
        self.overall_progress_label = ttk.Label(download_frame, text="")
        self.overall_progress_label.pack(anchor=W)
        
        # 多任务进度条容器（使用Canvas+Frame实现滚动）
        ttk.Label(download_frame, text="下载任务:").pack(anchor=W, pady=(10,0))
        
        self.tasks_container = ttk.Frame(download_frame)
        self.tasks_container.pack(fill=X, pady=2)
        
        # 初始化任务进度条列表
        self.task_widgets = []  # [(frame, progress_var, progress_bar, name_label, detail_label, speed_label), ...]
        self.create_task_progress_bars(1)  # 默认1个
        
        # 日志区域
        log_frame = ttk.LabelFrame(right_frame, text="日志", padding="5")
        log_frame.pack(fill=BOTH, expand=True)
        
        self.log_text = ScrolledText(log_frame, height=20, width=40)
        self.log_text.pack(fill=BOTH, expand=True)
        
        # 状态栏
        self.status_var = StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=SUNKEN, anchor=W)
        status_bar.pack(fill=X, side=BOTTOM, padx=10, pady=5)
        
        # 存储选中状态
        self.selected_items = set()
        
    def log(self, message):
        """添加日志"""
        self.log_text.insert(END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.see(END)
    
    def on_parallel_change(self, event=None):
        """并行数改变时更新进度条数量"""
        if not self.is_downloading:
            num = int(self.parallel_var.get())
            self.create_task_progress_bars(num)
    
    def create_task_progress_bars(self, num):
        """创建指定数量的任务进度条"""
        # 清除现有的进度条
        for widget_tuple in self.task_widgets:
            widget_tuple[0].destroy()
        self.task_widgets.clear()
        
        # 创建新的进度条
        for i in range(num):
            frame = ttk.LabelFrame(self.tasks_container, text=f"任务 {i+1}", padding="3")
            frame.pack(fill=X, pady=2)
            
            # 进度条
            progress_var = DoubleVar()
            progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100)
            progress_bar.pack(fill=X)
            
            # 文件名
            name_label = ttk.Label(frame, text="等待中...", wraplength=280, font=('TkDefaultFont', 8))
            name_label.pack(anchor=W)
            
            # 详情（大小）
            detail_label = ttk.Label(frame, text="", font=('TkDefaultFont', 8))
            detail_label.pack(anchor=W)
            
            # 速度
            speed_label = ttk.Label(frame, text="", font=('TkDefaultFont', 8))
            speed_label.pack(anchor=W)
            
            self.task_widgets.append((frame, progress_var, progress_bar, name_label, detail_label, speed_label))
        
    def browse_save_dir(self):
        """选择保存目录"""
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.save_dir_entry.delete(0, END)
            self.save_dir_entry.insert(0, dir_path)
    
    def save_cache(self):
        """保存扫描结果到缓存文件"""
        if not self.all_files:
            messagebox.showwarning("警告", "没有可保存的扫描结果！")
            return
        
        cache_data = {
            'url': self.url_entry.get(),
            'files': self.all_files,
            'scan_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.log(f"缓存已保存到 {self.cache_file}")
            messagebox.showinfo("成功", f"扫描结果已保存到 {self.cache_file}")
        except Exception as e:
            self.log(f"保存缓存失败: {e}")
            messagebox.showerror("错误", f"保存缓存失败: {e}")
    
    def load_cache(self):
        """从缓存文件加载扫描结果"""
        if not os.path.exists(self.cache_file):
            self.log("没有找到缓存文件")
            return False
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            self.all_files = cache_data.get('files', {})
            cached_url = cache_data.get('url', '')
            scan_time = cache_data.get('scan_time', '未知')
            
            # 清除路径缓存
            if hasattr(self, '_path_to_url_cache'):
                del self._path_to_url_cache
            
            if cached_url:
                self.url_entry.delete(0, END)
                self.url_entry.insert(0, cached_url)
            
            # 清空并重建树
            self.tree.delete(*self.tree.get_children())
            self.selected_items.clear()
            
            for url, info in self.all_files.items():
                self.add_to_tree(info['path'], url)
            
            self.file_count_label.config(text=f"共 {len(self.all_files)} 个文件")
            self.log(f"已加载缓存 (扫描时间: {scan_time})，共 {len(self.all_files)} 个文件")
            self.status_var.set(f"已加载缓存，共 {len(self.all_files)} 个文件")
            self.update_downloaded_count()
            return True
            
        except Exception as e:
            self.log(f"加载缓存失败: {e}")
            return False
    
    def load_downloaded_record(self, refresh_ui=True):
        """加载已下载记录"""
        if not os.path.exists(self.downloaded_record_file):
            return
        
        try:
            with open(self.downloaded_record_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.downloaded_files = set(data.get('downloaded', []))
            self.log(f"已加载下载记录，{len(self.downloaded_files)} 个文件已下载")
            self.update_downloaded_count()
            # 刷新树形视图以显示已下载标记
            if refresh_ui:
                self.apply_filter()
        except Exception as e:
            self.log(f"加载下载记录失败: {e}")
    
    def save_downloaded_record(self):
        """保存已下载记录"""
        try:
            data = {
                'downloaded': list(self.downloaded_files),
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.downloaded_record_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存下载记录失败: {e}")
    
    def load_failed_record(self, refresh_ui=True):
        """加载下载失败记录"""
        if not os.path.exists(self.failed_record_file):
            return
        
        try:
            with open(self.failed_record_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.failed_files = set(data.get('failed', []))
            self.log(f"已加载失败记录，{len(self.failed_files)} 个文件下载失败")
            self.update_failed_count()
            if refresh_ui:
                self.apply_filter()
        except Exception as e:
            self.log(f"加载失败记录失败: {e}")
    
    def save_failed_record(self):
        """保存下载失败记录"""
        try:
            data = {
                'failed': list(self.failed_files),
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.failed_record_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存失败记录失败: {e}")
    
    def mark_as_failed(self, relative_path):
        """标记文件为下载失败"""
        self.failed_files.add(relative_path)
        # 确保不在成功列表中
        self.downloaded_files.discard(relative_path)
        self.save_failed_record()
        self.save_downloaded_record()
        
        # 使用root.after确保UI更新在主线程执行
        def update_ui():
            self.update_failed_count()
            self.update_downloaded_count()
            # 更新树形视图中的显示 - 红色
            if self.tree.exists(relative_path):
                current_tags = list(self.tree.item(relative_path, 'tags'))
                # 移除downloaded标签，添加failed标签
                if 'downloaded' in current_tags:
                    current_tags.remove('downloaded')
                if 'failed' not in current_tags:
                    current_tags.append('failed')
                self.tree.item(relative_path, tags=tuple(current_tags))
                # 强制刷新显示
                self.tree.update_idletasks()
        
        self.root.after(0, update_ui)
    
    def mark_as_downloaded(self, relative_path):
        """标记文件为已下载"""
        self.downloaded_files.add(relative_path)
        # 从失败列表中移除
        if relative_path in self.failed_files:
            self.failed_files.discard(relative_path)
            self.save_failed_record()
        self.save_downloaded_record()
        
        # 使用root.after确保UI更新在主线程执行
        def update_ui():
            self.update_failed_count()
            self.update_downloaded_count()
            # 更新树形视图中的显示 - 蓝色
            if self.tree.exists(relative_path):
                current_tags = list(self.tree.item(relative_path, 'tags'))
                # 移除failed标签，添加downloaded标签
                if 'failed' in current_tags:
                    current_tags.remove('failed')
                if 'downloaded' not in current_tags:
                    current_tags.append('downloaded')
                self.tree.item(relative_path, tags=tuple(current_tags))
                # 强制刷新显示
                self.tree.update_idletasks()
        
        self.root.after(0, update_ui)
    
    def update_failed_count(self):
        """更新失败计数"""
        count = len(self.failed_files)
        self.failed_count_label.config(text=f"失败: {count}")
    
    def update_downloaded_count(self):
        """更新已下载计数"""
        count = len(self.downloaded_files)
        self.downloaded_count_label.config(text=f"已下载: {count}")
    
    def toggle_file_view(self):
        """切换显示全部/仅未下载"""
        self.show_all_files = not self.show_all_files
        if self.show_all_files:
            self.show_all_var.set("显示全部")
        else:
            self.show_all_var.set("仅未下载")
        self.apply_filter()
    
    def show_context_menu(self, event):
        """显示右键菜单"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def get_all_children_files(self, item):
        """获取某个节点下的所有文件（递归）"""
        files = []
        children = self.tree.get_children(item)
        
        if not children:
            # 如果没有子节点，检查是否是文件
            tags = self.tree.item(item, 'tags')
            if 'file' in tags:
                files.append(item)
        else:
            # 递归获取所有子节点的文件
            for child in children:
                files.extend(self.get_all_children_files(child))
        
        return files
    
    def select_folder(self):
        """选中当前文件夹下的所有文件"""
        item = self.tree.focus()
        if not item:
            messagebox.showwarning("警告", "请先选择一个文件夹！")
            return
        
        files = self.get_all_children_files(item)
        
        # 如果当前选中的就是文件，也加入
        tags = self.tree.item(item, 'tags')
        if 'file' in tags:
            files.append(item)
        
        for file_item in files:
            self.selected_items.add(file_item)
            if self.tree.exists(file_item):
                self.tree.set(file_item, 'selected', '☑')
        
        self.update_selected_count()
        self.log(f"已选中 {len(files)} 个文件")
    
    def deselect_folder(self):
        """取消选中当前文件夹下的所有文件"""
        item = self.tree.focus()
        if not item:
            messagebox.showwarning("警告", "请先选择一个文件夹！")
            return
        
        files = self.get_all_children_files(item)
        
        # 如果当前选中的就是文件，也处理
        tags = self.tree.item(item, 'tags')
        if 'file' in tags:
            files.append(item)
        
        for file_item in files:
            self.selected_items.discard(file_item)
            if self.tree.exists(file_item):
                self.tree.set(file_item, 'selected', '☐')
        
        self.update_selected_count()
        self.log(f"已取消选中 {len(files)} 个文件")
    
    def expand_all(self):
        """展开所有节点"""
        def expand_recursive(item):
            self.tree.item(item, open=True)
            for child in self.tree.get_children(item):
                expand_recursive(child)
        
        for item in self.tree.get_children():
            expand_recursive(item)
    
    def collapse_all(self):
        """折叠所有节点"""
        def collapse_recursive(item):
            for child in self.tree.get_children(item):
                collapse_recursive(child)
            self.tree.item(item, open=False)
        
        for item in self.tree.get_children():
            collapse_recursive(item)
            
    def start_scan(self):
        """开始扫描"""
        if self.is_scanning:
            return
        self.is_scanning = True
        self.scan_btn.config(state=DISABLED)
        self.all_files.clear()
        self.selected_items.clear()
        self.tree.delete(*self.tree.get_children())
        self.log("开始扫描文件...")
        
        thread = threading.Thread(target=self.scan_files, daemon=True)
        thread.start()
        
    def scan_files(self):
        """扫描文件（后台线程）- 使用多线程加速"""
        target_url = self.url_entry.get()
        
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.page_load_strategy = 'eager'  # 加速页面加载
            
            self.root.after(0, lambda: self.status_var.set("正在启动浏览器..."))
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            
            self.root.after(0, lambda: self.status_var.set(f"正在访问: {target_url}"))
            self.driver.get(target_url)
            time.sleep(3)
            
            # 尝试展开文件树
            self.root.after(0, lambda: self.status_var.set("正在展开文件树..."))
            try:
                expand_script = """
                if (typeof $ !== 'undefined' && $.jstree) {
                    $('.jstree').jstree('open_all');
                }
                if (typeof $ !== 'undefined' && $.ui && $.ui.fancytree) {
                    $.ui.fancytree.getTree().expandAll();
                }
                document.querySelectorAll('.jstree-closed, .fancytree-expander').forEach(el => el.click());
                """
                self.driver.execute_script(expand_script)
                time.sleep(2)
            except:
                pass
            
            target_extensions = ('.nc', '.xlsx', '.xls', '.csv', '.zip', '.pdf')
            found_urls = set()
            stable_count = 0
            
            self.root.after(0, lambda: self.status_var.set("正在收集文件链接..."))
            
            # 快速收集所有链接
            while stable_count < 2:
                elems = self.driver.find_elements(By.TAG_NAME, "a")
                new_count = 0
                
                # 批量获取href属性
                hrefs = self.driver.execute_script("""
                    var links = document.querySelectorAll('a');
                    var hrefs = [];
                    for (var i = 0; i < links.length; i++) {
                        if (links[i].href) hrefs.push(links[i].href);
                    }
                    return hrefs;
                """)
                
                for href in hrefs:
                    if href and href not in found_urls and href.lower().endswith(target_extensions):
                        found_urls.add(href)
                        new_count += 1
                
                if new_count == 0:
                    stable_count += 1
                else:
                    stable_count = 0
                    
                self.root.after(0, lambda c=len(found_urls): self.status_var.set(f"已发现 {c} 个文件链接..."))
                
                try:
                    self.driver.execute_script("window.scrollBy(0, 1000);")
                    self.driver.execute_script("""
                        document.querySelectorAll('.jstree-closed').forEach(el => {
                            var icon = el.querySelector('.jstree-icon');
                            if (icon) icon.click();
                        });
                    """)
                except:
                    pass
                time.sleep(0.5)
            
            # 关闭浏览器，释放资源
            if self.driver:
                self.driver.quit()
                self.driver = None
            
            self.root.after(0, lambda c=len(found_urls): self.status_var.set(f"正在处理 {c} 个文件..."))
            self.root.after(0, lambda c=len(found_urls): self.log(f"发现 {c} 个文件链接，正在获取文件大小..."))
            
            # 先快速处理路径，不获取大小
            for href in found_urls:
                relative_path = self.get_relative_path(href, target_url)
                if not relative_path:
                    relative_path = unquote(href.split("/")[-1])
                self.all_files[href] = {'path': relative_path, 'size': '获取中...', 'size_bytes': 0}
            
            # 先显示文件列表
            def add_all_to_tree_initial():
                for url, info in self.all_files.items():
                    self.add_to_tree(info['path'], url)
                self.file_count_label.config(text=f"共 {len(self.all_files)} 个文件")
            
            self.root.after(0, add_all_to_tree_initial)
            
            # 使用更多线程并行获取文件大小（使用Session复用连接）
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            processed_count = [0]  # 使用列表以便在闭包中修改
            total_count = len(found_urls)
            lock = threading.Lock()
            
            def get_file_size(href):
                file_size = 0
                size_str = '未知'
                try:
                    response = session.head(href, timeout=5, allow_redirects=True)
                    if response.status_code == 200:
                        content_length = response.headers.get('content-length')
                        if content_length:
                            file_size = int(content_length)
                            size_str = format_size(file_size)
                    elif response.status_code == 405:  # HEAD不支持，尝试GET
                        response = session.get(href, timeout=5, stream=True, allow_redirects=True)
                        content_length = response.headers.get('content-length')
                        if content_length:
                            file_size = int(content_length)
                            size_str = format_size(file_size)
                        response.close()
                except:
                    pass
                
                # 更新进度
                with lock:
                    processed_count[0] += 1
                    if processed_count[0] % 20 == 0 or processed_count[0] == total_count:
                        p, t = processed_count[0], total_count
                        self.root.after(0, lambda p=p, t=t: self.status_var.set(f"获取文件大小: {p}/{t}"))
                
                return href, file_size, size_str
            
            # 使用更多线程并行处理 (32-64个线程大幅加速)
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(get_file_size, url) for url in found_urls]
                
                for future in as_completed(futures):
                    try:
                        href, file_size, size_str = future.result()
                        if href in self.all_files:
                            self.all_files[href]['size'] = size_str
                            self.all_files[href]['size_bytes'] = file_size
                    except:
                        continue
            
            session.close()
            
            # 刷新树形视图显示文件大小
            self.root.after(0, lambda: self.status_var.set("正在更新文件列表..."))
            
            def refresh_tree():
                self.apply_filter()
                self.file_count_label.config(text=f"共 {len(self.all_files)} 个文件")
            
            self.root.after(0, refresh_tree)
            
            self.root.after(0, lambda: self.log(f"扫描完成，共发现 {len(self.all_files)} 个文件"))
            self.root.after(0, lambda: self.status_var.set(f"扫描完成，共 {len(self.all_files)} 个文件"))
            
            # 自动保存缓存
            self.root.after(0, self.save_cache)
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"扫描出错: {e}"))
            self.root.after(0, lambda: messagebox.showerror("错误", f"扫描出错: {e}"))
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
            self.is_scanning = False
            self.root.after(0, lambda: self.scan_btn.config(state=NORMAL))
    
    def get_relative_path(self, url, base_url):
        """从URL中提取相对路径"""
        parsed = urlparse(url)
        path = unquote(parsed.path)
        base_parsed = urlparse(base_url)
        base_path = base_parsed.path.rstrip('/')
        
        if path.startswith(base_path):
            path = path[len(base_path):]
        return path.lstrip('/')
    
    def add_to_tree(self, relative_path, url):
        """添加文件到树形视图"""
        parts = relative_path.split('/')
        parent = ''
        
        for i, part in enumerate(parts[:-1]):
            item_id = '/'.join(parts[:i+1])
            if not self.tree.exists(item_id):
                self.tree.insert(parent, END, item_id, text=part, open=True)
            parent = item_id
        
        # 添加文件节点
        file_id = relative_path
        if not self.tree.exists(file_id):
            # 检查状态
            is_downloaded = relative_path in self.downloaded_files
            is_failed = relative_path in self.failed_files
            tags = ['file', url]
            if is_downloaded:
                tags.append('downloaded')
            elif is_failed:
                tags.append('failed')
            
            # 直接从url获取文件大小（不再遍历）
            size_str = ''
            if url in self.all_files:
                size_str = self.all_files[url].get('size', '')
            
            self.tree.insert(parent, END, file_id, text=parts[-1], values=(size_str, '☐'), tags=tuple(tags))
    
    def toggle_item(self, event=None):
        """切换选中状态"""
        item = self.tree.focus()
        if not item:
            return
            
        # 检查是否是文件（非文件夹）
        tags = self.tree.item(item, 'tags')
        if 'file' not in tags:
            return
            
        if item in self.selected_items:
            self.selected_items.discard(item)
            self.tree.set(item, 'selected', '☐')
        else:
            self.selected_items.add(item)
            self.tree.set(item, 'selected', '☑')
        
        self.update_selected_count()
    
    def update_selected_count(self):
        """更新选中数量和总大小"""
        count = len(self.selected_items)
        total_size_bytes = 0
        
        # 构建path到url的映射（只在需要时）
        if count > 0:
            # 使用path_to_url缓存加速查找
            if not hasattr(self, '_path_to_url_cache') or len(self._path_to_url_cache) != len(self.all_files):
                self._path_to_url_cache = {info['path']: url for url, info in self.all_files.items()}
            
            for path in self.selected_items:
                url = self._path_to_url_cache.get(path)
                if url and url in self.all_files:
                    total_size_bytes += self.all_files[url].get('size_bytes', 0)
        
        # 转换为GB，保留一位小数
        total_size_gb = total_size_bytes / (1024 * 1024 * 1024)
        self.selected_count_label.config(text=f"已选择: {count} 个文件 ({total_size_gb:.1f} GB)")
    
    def select_all(self):
        """全选"""
        for url, info in self.all_files.items():
            item = info['path']
            if self.tree.exists(item):
                self.selected_items.add(item)
                self.tree.set(item, 'selected', '☑')
        self.update_selected_count()
    
    def deselect_all(self):
        """取消全选"""
        for item in list(self.selected_items):
            if self.tree.exists(item):
                self.tree.set(item, 'selected', '☐')
        self.selected_items.clear()
        self.update_selected_count()
    
    def exclude_downloaded(self):
        """从已选择的文件中排除已下载的文件"""
        excluded_count = 0
        for item in list(self.selected_items):
            if item in self.downloaded_files:
                self.selected_items.discard(item)
                if self.tree.exists(item):
                    self.tree.set(item, 'selected', '☐')
                excluded_count += 1
        
        self.update_selected_count()
        if excluded_count > 0:
            self.log(f"已排除 {excluded_count} 个已下载的文件")
        else:
            self.log("没有需要排除的已下载文件")
    
    def invert_selection(self):
        """反选"""
        for url, info in self.all_files.items():
            item = info['path']
            if self.tree.exists(item):
                if item in self.selected_items:
                    self.selected_items.discard(item)
                    self.tree.set(item, 'selected', '☐')
                else:
                    self.selected_items.add(item)
                    self.tree.set(item, 'selected', '☑')
        self.update_selected_count()
    
    def apply_filter(self, event=None):
        """应用筛选"""
        filter_text = self.filter_entry.get().lower()
        ext_filter = self.ext_var.get()
        
        # 清空树并重新添加匹配项
        self.tree.delete(*self.tree.get_children())
        
        displayed_count = 0
        for url, info in self.all_files.items():
            path = info['path']
            
            # 检查是否只显示未下载
            if not self.show_all_files and path in self.downloaded_files:
                continue
            
            # 检查文件类型筛选
            if ext_filter != '全部' and not path.lower().endswith(ext_filter):
                continue
                
            # 检查文本筛选
            if filter_text and filter_text not in path.lower():
                continue
            
            self.add_to_tree(path, url)
            displayed_count += 1
            
            # 恢复选中状态
            if path in self.selected_items and self.tree.exists(path):
                self.tree.set(path, 'selected', '☑')
        
        # 更新显示的文件数量
        if self.show_all_files:
            self.file_count_label.config(text=f"共 {len(self.all_files)} 个文件")
        else:
            self.file_count_label.config(text=f"显示 {displayed_count} / {len(self.all_files)} 个文件")
    
    def start_download(self):
        """开始下载"""
        if not self.selected_items:
            messagebox.showwarning("警告", "请先选择要下载的文件！")
            return
            
        self.is_downloading = True
        self.stop_download = False
        self.download_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.parallel_combo.config(state=DISABLED)
        
        # 确保进度条数量正确
        num_parallel = int(self.parallel_var.get())
        self.create_task_progress_bars(num_parallel)
        
        thread = threading.Thread(target=self.download_files_parallel, daemon=True)
        thread.start()
    
    def stop_download_func(self):
        """停止下载"""
        self.stop_download = True
        self.log("正在停止下载...")
    
    def download_single_file(self, task_id, url, relative_path, save_dir, stats):
        """下载单个文件（供线程池使用）- 带重试机制"""
        headers = {"User-Agent": "Mozilla/5.0"}
        file_path = os.path.join(save_dir, relative_path)
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(relative_path)
        
        # 获取对应的进度条组件
        if task_id < len(self.task_widgets):
            _, progress_var, _, name_label, detail_label, speed_label = self.task_widgets[task_id]
        else:
            return False
        
        try:
            if file_dir and not os.path.exists(file_dir):
                os.makedirs(file_dir, exist_ok=True)
            
            # 更新UI - 文件名
            self.root.after(0, lambda: name_label.config(text=f"{file_name}"))
            self.root.after(0, lambda: progress_var.set(0))
            self.root.after(0, lambda: detail_label.config(text="正在连接..."))
            self.root.after(0, lambda: speed_label.config(text=""))
            
            self.root.after(0, lambda rp=relative_path: self.log(f"[任务{task_id+1}] 下载: {rp}"))
            
            if os.path.exists(file_path):
                self.root.after(0, lambda: self.log(f"[任务{task_id+1}] 文件已存在，跳过"))
                self.root.after(0, lambda: detail_label.config(text="已存在，跳过"))
                self.root.after(0, lambda: progress_var.set(100))
                with stats['lock']:
                    stats['skipped'] += 1
                return True
            
            # 重试机制
            last_error = None
            for retry in range(self.max_retries):
                try:
                    if self.stop_download:
                        raise Exception("用户取消")
                    
                    if retry > 0:
                        self.root.after(0, lambda r=retry: detail_label.config(text=f"重试 {r}/{self.max_retries-1}..."))
                        self.root.after(0, lambda r=retry: self.log(f"[任务{task_id+1}] 第 {r} 次重试..."))
                        time.sleep(self.retry_delay)
                    
                    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        total_size = int(r.headers.get('content-length', 0))
                        downloaded = 0
                        start_time = time.time()
                        last_update_time = start_time
                        last_downloaded = 0
                        
                        size_str = format_size(total_size) if total_size > 0 else "未知"
                        self.root.after(0, lambda s=size_str: detail_label.config(text=f"0 B / {s}"))
                        
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=65536):
                                if self.stop_download:
                                    raise Exception("用户取消")
                                size = f.write(chunk)
                                downloaded += size
                                
                                current_time = time.time()
                                if current_time - last_update_time >= 0.3:
                                    elapsed = current_time - last_update_time
                                    speed = (downloaded - last_downloaded) / elapsed if elapsed > 0 else 0
                                    last_update_time = current_time
                                    last_downloaded = downloaded
                                    
                                    if total_size > 0:
                                        file_progress = (downloaded / total_size) * 100
                                        self.root.after(0, lambda p=file_progress: progress_var.set(p))
                                    
                                    downloaded_str = format_size(downloaded)
                                    total_str = format_size(total_size) if total_size > 0 else "未知"
                                    speed_str = format_speed(speed)
                                    
                                    if speed > 0 and total_size > 0:
                                        remaining = (total_size - downloaded) / speed
                                        if remaining < 60:
                                            eta = f"{remaining:.0f}秒"
                                        elif remaining < 3600:
                                            eta = f"{remaining/60:.1f}分"
                                        else:
                                            eta = f"{remaining/3600:.1f}时"
                                    else:
                                        eta = "..."
                                    
                                    self.root.after(0, lambda d=downloaded_str, t=total_str: 
                                                   detail_label.config(text=f"{d} / {t}"))
                                    self.root.after(0, lambda s=speed_str, e=eta: 
                                                   speed_label.config(text=f"{s} | 剩余: {e}"))
                        
                        # 下载成功
                        self.root.after(0, lambda: progress_var.set(100))
                        self.root.after(0, lambda: detail_label.config(text="完成"))
                        self.root.after(0, lambda: speed_label.config(text=""))
                        self.root.after(0, lambda rp=relative_path: self.mark_as_downloaded(rp))
                        with stats['lock']:
                            stats['completed'] += 1
                        return True
                        
                except Exception as e:
                    last_error = e
                    if str(e) == "用户取消":
                        raise
                    # 删除可能不完整的文件
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except:
                            pass
                    continue
            
            # 所有重试都失败
            error_msg = str(last_error)[:30] if last_error else "未知错误"
            self.root.after(0, lambda e=error_msg: detail_label.config(text=f"失败: {e}"))
            self.root.after(0, lambda: speed_label.config(text=""))
            self.root.after(0, lambda rp=relative_path: self.log(f"[任务{task_id+1}] 下载失败(重试{self.max_retries}次): {rp}"))
            self.root.after(0, lambda rp=relative_path: self.mark_as_failed(rp))
            with stats['lock']:
                stats['failed'] += 1
            return False
                    
        except Exception as e:
            if str(e) != "用户取消":
                error_msg = str(e)[:30]
                self.root.after(0, lambda e=error_msg: detail_label.config(text=f"错误: {e}"))
                self.root.after(0, lambda e=e: self.log(f"[任务{task_id+1}] 下载出错: {e}"))
                self.root.after(0, lambda rp=relative_path: self.mark_as_failed(rp))
                with stats['lock']:
                    stats['failed'] += 1
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return False
    
    def download_files_parallel(self):
        """并行下载文件"""
        save_dir = self.save_dir_entry.get()
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        # 构建下载列表
        download_list = []
        for url, info in self.all_files.items():
            if info['path'] in self.selected_items:
                download_list.append((url, info['path']))
        
        total_files = len(download_list)
        num_parallel = int(self.parallel_var.get())
        
        # 统计信息（线程安全）
        stats = {
            'completed': 0,
            'skipped': 0,
            'failed': 0,
            'lock': threading.Lock()
        }
        
        # 任务队列
        task_queue = queue.Queue()
        for item in download_list:
            task_queue.put(item)
        
        # 更新总体进度的函数
        def update_overall_progress():
            while not self.stop_download:
                with stats['lock']:
                    done = stats['completed'] + stats['skipped'] + stats['failed']
                progress = (done / total_files) * 100 if total_files > 0 else 0
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                self.root.after(0, lambda d=done, t=total_files, c=stats['completed'], s=stats['skipped'], f=stats['failed']: 
                               self.overall_progress_label.config(text=f"进度: {d}/{t} | 完成: {c} | 跳过: {s} | 失败: {f}"))
                if done >= total_files:
                    break
                time.sleep(0.5)
        
        # 启动进度更新线程
        progress_thread = threading.Thread(target=update_overall_progress, daemon=True)
        progress_thread.start()
        
        # 工作线程函数
        def worker(task_id):
            while not self.stop_download:
                try:
                    url, relative_path = task_queue.get_nowait()
                except queue.Empty:
                    break
                
                self.download_single_file(task_id, url, relative_path, save_dir, stats)
                task_queue.task_done()
            
            # 任务完成，清空显示
            if task_id < len(self.task_widgets):
                _, progress_var, _, name_label, detail_label, speed_label = self.task_widgets[task_id]
                self.root.after(0, lambda: name_label.config(text="已完成"))
                self.root.after(0, lambda: detail_label.config(text=""))
                self.root.after(0, lambda: speed_label.config(text=""))
        
        # 启动工作线程
        threads = []
        for i in range(num_parallel):
            t = threading.Thread(target=worker, args=(i,), daemon=True)
            t.start()
            threads.append(t)
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 等待进度线程
        progress_thread.join(timeout=1)
        
        # 完成
        self.root.after(0, lambda: self.progress_var.set(100))
        self.root.after(0, lambda c=stats['completed'], s=stats['skipped'], f=stats['failed']: 
                       self.log(f"下载任务完成！成功: {c}, 跳过: {s}, 失败: {f}"))
        self.root.after(0, lambda c=stats['completed'], s=stats['skipped'], f=stats['failed']: 
                       self.overall_progress_label.config(text=f"完成! 成功: {c} | 跳过: {s} | 失败: {f}"))
        self.root.after(0, lambda: self.download_btn.config(state=NORMAL))
        self.root.after(0, lambda: self.stop_btn.config(state=DISABLED))
        self.root.after(0, lambda: self.parallel_combo.config(state="readonly"))
        self.is_downloading = False

def main():
    root = Tk()
    app = GCBDownloader(root)
    root.mainloop()

if __name__ == "__main__":
    main()
