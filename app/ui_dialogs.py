# -*- coding: utf-8 -*-
"""
app/ui_dialogs.py —— 四个对话框

职责：
1. SubjectDialog：新建科目 / 给科目改名的输入小窗口；
2. NodeDialog：节点详情窗（标题、文字描述、笔记图片、保存、关闭、删除本节点）；
3. CalendarDialog：复习月历窗（看哪天忘了什么、点日期看当天、右键撤销标记）；
   年份、月份直接写进输入框（或点小箭头）就能跳月，没有「上一月 / 下一月」按钮；
4. HelpDialog：使用帮助窗（任务 04），只读、可滚动、可关闭。

说明：
- 本文件只负责界面与输入校验，真正的读写数据库都调用 app\\db.py；
- SubjectDialog 是模态小窗口；NodeDialog 不是模态，可以同时打开多个，
  主界面的科目、节点列表仍然可以点击；
- 节点详情窗的图片区底部有「添加图片」按钮，和在表格空白处右键「添加图片」
  效果完全一样；在图片行上右键可以删除或重命名；
  按住图片行上下拖动即可调整顺序，拖动中的行会标蓝；
- 「关闭」不保存；内容改过又点关闭时，会先问一句是否确定放弃改动；
- 笔记图片只显示文件名，不做缩略图，也不用 Pillow；
- 四种添加方式（按钮、拖放、Ctrl+V、右键菜单）最终都调用同一个 _add_images 方法；
- 日历窗是独立窗口，同时只开一个（由主界面 ui_main.py 控制）；
  格子颜色只看「当前科目 + 当前显示月份」的标记数量，不掺别的科目。
"""

import calendar
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk

from tkinterdnd2 import DND_FILES

import db
import dates


def _place_centered(window, parent, width=None, height=None):
    """把对话框摆到父窗口中间偏上的位置。"""
    window.update_idletasks()
    if width is None:
        width = window.winfo_reqwidth()
    if height is None:
        height = window.winfo_reqheight()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 3)
    window.geometry('%dx%d+%d+%d' % (width, height, x, y))


def _clipboard_file_paths(window):
    """
    从剪贴板里取「文件列表」。

    Windows 资源管理器复制文件后，剪贴板里会有一份文本，
    内容是每行一个完整路径。这里逐行取，并只保留真实存在的文件。

    注意：不能用 tk.splitlist，因为文件名里带空格时会被拆坏。
    """
    try:
        text = window.clipboard_get()
    except tk.TclError:
        return []

    if not isinstance(text, str):
        return []

    paths = []
    for line in text.splitlines():
        candidate = line.strip().strip('"').strip("'")
        if candidate and os.path.isfile(candidate):
            paths.append(candidate)
    return paths


def _clipboard_has_bitmap():
    """
    判断剪贴板里是不是「截图位图」。

    本任务没有装 Pillow，位图无法直接保存成文件，
    所以只用来给用户一句明确提示，而不是静默失败。

    Windows 剪贴板格式编号：
        2  = CF_BITMAP
        8  = CF_DIB
        17 = CF_DIBV5
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        return bool(
            user32.IsClipboardFormatAvailable(8)
            or user32.IsClipboardFormatAvailable(2)
            or user32.IsClipboardFormatAvailable(17)
        )
    except Exception:
        # 判断失败时当作没有位图，避免影响正常粘贴
        return False


class SubjectDialog:
    """新建科目 / 科目改名的对话框。关掉后从 result_id 取新科目 id。"""

    def __init__(self, parent, mode, subject=None):
        # mode 只能是 'create'（新建）或 'rename'（改名）
        self.parent = parent
        self.mode = mode
        self.subject = subject
        self.result_id = None

        self.window = tk.Toplevel(parent)
        if mode == 'rename':
            self.window.title('科目改名')
        else:
            self.window.title('新建科目')
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.protocol('WM_DELETE_WINDOW', self._on_cancel)

        body = ttk.Frame(self.window, padding=14)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text='科目名称：').grid(row=0, column=0, sticky='w')
        self.name_var = tk.StringVar()
        if subject is not None:
            self.name_var.set(subject['name'])
        self.name_entry = ttk.Entry(body, textvariable=self.name_var, width=32)
        self.name_entry.grid(row=0, column=1, sticky='ew', padx=(6, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=1, column=0, columnspan=2, sticky='e', pady=(14, 0))
        ttk.Button(buttons, text='确定', command=self._on_ok).pack(side='left')
        ttk.Button(buttons, text='取消', command=self._on_cancel).pack(
            side='left', padx=(8, 0)
        )

        _place_centered(self.window, parent)
        self.name_entry.focus_set()
        self.window.grab_set()

    def _on_ok(self):
        """点「确定」：校验名称、写数据库、记下科目 id、关闭窗口。"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning('提示', '科目名称不能为空。', parent=self.window)
            self.name_entry.focus_set()
            return
        if self.mode == 'rename' and self.subject is not None:
            db.rename_subject(self.subject['id'], name)
            self.result_id = self.subject['id']
        else:
            self.result_id = db.create_subject(name)
        self.window.destroy()

    def _on_cancel(self):
        """点「取消」或右上角叉：什么都不写，直接关闭。"""
        self.window.destroy()


class NodeDialog:
    """
    节点详情窗。

    用法：
    - 新建节点：NodeDialog(parent, subject_id=当前科目 id)，保存后 saved 为 True；
    - 打开已有节点：NodeDialog(parent, node=节点数据行)，保存后 saved 为 True，
      在里面删掉节点后 deleted 为 True；
    - on_closed：窗口真正关闭前调用，参数是这个 NodeDialog 自己，
      主界面用它刷新列表、更新「[N 图]」标记。

    这个窗口没有 grab_set，不锁主界面，可以同时打开多个节点详情；
    新节点还没有数据库 id，图片表格为空，此时添加图片会提示先保存。
    """

    def __init__(self, parent, node=None, subject_id=None, on_closed=None):
        self.parent = parent
        self.node = node
        self.subject_id = subject_id
        self.node_id = node['id'] if node is not None else None
        self.saved = False
        self.deleted = False
        self.on_closed = on_closed
        # 当前列表里的图片记录，顺序与表格一致
        self.images = []
        # 拖动排序时用到的状态
        self._drag_image_id = None
        self._drag_started = False
        self._drag_press_y = 0

        self.window = tk.Toplevel(parent)
        if node is None:
            self.window.title('新建节点')
        else:
            self.window.title('节点详情')
        # 故意不调用 transient 和 grab_set：
        # 这样主界面仍可点击，也能同时打开好几个节点详情窗。
        self.window.minsize(660, 600)
        self.window.protocol('WM_DELETE_WINDOW', self._on_close)

        body = ttk.Frame(self.window, padding=12)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=3)
        body.rowconfigure(3, weight=2)

        ttk.Label(body, text='标题：').grid(row=0, column=0, sticky='w')
        self.title_var = tk.StringVar()
        if node is not None:
            self.title_var.set(node['title'])
        self.title_entry = ttk.Entry(body, textvariable=self.title_var)
        self.title_entry.grid(row=0, column=1, sticky='ew', padx=(6, 0))

        ttk.Label(body, text='文字描述：').grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(10, 4)
        )

        text_frame = ttk.Frame(body)
        text_frame.grid(row=2, column=0, columnspan=2, sticky='nsew')
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.content_text = tk.Text(text_frame, wrap='word', height=8)
        self.content_text.grid(row=0, column=0, sticky='nsew')
        text_scroll = ttk.Scrollbar(
            text_frame, orient='vertical', command=self.content_text.yview
        )
        text_scroll.grid(row=0, column=1, sticky='ns')
        self.content_text.configure(yscrollcommand=text_scroll.set)
        if node is not None:
            self.content_text.insert('1.0', node['content'])

        self._build_images_area(body)

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(12, 0))
        ttk.Button(buttons, text='保存', command=self._on_save).pack(side='left')
        self.delete_button = ttk.Button(
            buttons, text='删除本节点', command=self._on_delete
        )
        self.delete_button.pack(side='left', padx=(8, 0))
        if self.node_id is None:
            # 新节点还没存进数据库，没有可删的东西
            self.delete_button.configure(state='disabled')
        ttk.Button(buttons, text='关闭', command=self._on_close).pack(side='right')

        # 记下打开窗口时的原始内容，用来判断有没有改过
        self._original = self._current_values()

        # 先把图片列表填好，再登记拖放目标和 Ctrl+V
        self._refresh_images()
        self._register_drop_targets()

        _place_centered(self.window, parent, 820, 700)
        self.title_entry.focus_set()

    # ------------------------------------------------------------------
    # 笔记图片区域
    # ------------------------------------------------------------------

    def _build_images_area(self, body):
        """
        搭出「笔记图片」区域：两列表格 + 表格下方一个「添加图片」按钮。

        操作方式（四种方式等价，最终都调用 _add_images）：
        - 点「添加图片」按钮：弹出文件选择框；
        - 右键表格空白处：添加图片；
        - 把图片文件拖进窗口；
        - 在资源管理器复制图片文件后按 Ctrl+V；
        另外：
        - 右键某张图片：删除图片 / 重命名；
        - 按住某张图片上下拖动：调整顺序，拖动中的行标蓝；
        - 双击某张图片：用系统默认程序打开原图。
        """
        images = ttk.LabelFrame(body, text='笔记图片', padding=6)
        images.grid(
            row=3, column=0, columnspan=2, sticky='nsew', pady=(10, 0)
        )
        images.columnconfigure(0, weight=1)
        images.rowconfigure(0, weight=1)
        self.images_frame = images

        self.image_tree = ttk.Treeview(
            images,
            columns=('order', 'filename'),
            show='headings',
            selectmode='browse',
            height=10,
        )
        self.image_tree.heading('order', text='序号')
        self.image_tree.heading('filename', text='文件名')
        self.image_tree.column(
            'order', width=60, minwidth=50, anchor='center', stretch=False
        )
        self.image_tree.column(
            'filename', width=620, minwidth=200, anchor='w', stretch=True
        )
        self.image_tree.grid(row=0, column=0, sticky='nsew')

        image_scroll = ttk.Scrollbar(
            images, orient='vertical', command=self.image_tree.yview
        )
        image_scroll.grid(row=0, column=1, sticky='ns')
        self.image_tree.configure(yscrollcommand=image_scroll.set)

        # 图片区底部的「添加图片」按钮：和右键菜单、拖放、Ctrl+V 走同一个入口。
        # 任务 04 的帮助里写了「点按钮选文件」，所以这里补上这个按钮，
        # 让帮助说明和实际界面保持一致。
        add_image_button = ttk.Button(
            images, text='添加图片', command=self._on_add_images
        )
        add_image_button.grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(6, 0)
        )

        # 拖动中的行用浅蓝色背景标出来，表示「正在拖这一行」
        self.image_tree.tag_configure('dragging', background='#cce5ff')

        # 图片行右键菜单：删除、重命名
        self.image_row_menu = tk.Menu(self.window, tearoff=0)
        self.image_row_menu.add_command(
            label='删除图片',
            command=lambda: self.window.after_idle(self._on_delete_image),
        )
        self.image_row_menu.add_command(
            label='重命名',
            command=lambda: self.window.after_idle(self._on_rename_image),
        )

        # 表格空白处右键菜单：添加图片
        self.image_blank_menu = tk.Menu(self.window, tearoff=0)
        self.image_blank_menu.add_command(
            label='添加图片',
            command=lambda: self.window.after_idle(self._on_add_images),
        )

        self.image_tree.bind('<Double-1>', self._on_image_double_click)
        self.image_tree.bind('<Button-3>', self._on_image_right_click)
        self.image_tree.bind('<ButtonPress-1>', self._on_image_press)
        self.image_tree.bind('<B1-Motion>', self._on_image_motion)
        # 松开鼠标可能发生在表格外，所以绑在窗口上，保证一定能收尾
        self.window.bind('<ButtonRelease-1>', self._on_image_release, add='+')

        # 右键表格外面的空白边框，也当作「空白处」处理
        self.images_frame.bind('<Button-3>', self._on_images_blank_right_click)

    def _refresh_images(self):
        """按数据库里的顺序刷新表格；序号从 1 开始连续显示。"""
        self.image_tree.delete(*self.image_tree.get_children())
        self.images = []

        if self.node_id is None:
            return

        self.images = db.list_node_images(self.node_id)
        for index, image in enumerate(self.images, start=1):
            self.image_tree.insert(
                '',
                'end',
                iid=str(image['id']),
                values=(index, image['filename']),
            )

    def _renumber_image_rows(self):
        """
        只重排表格里显示的序号，不写数据库。

        拖动过程中每挪一次就调用一次，让「序号」立刻跟着变；
        真正的顺序等松开鼠标后再一次性写进数据库。
        """
        for index, item_id in enumerate(self.image_tree.get_children(), start=1):
            values = self.image_tree.item(item_id, 'values')
            filename = values[1] if len(values) > 1 else ''
            self.image_tree.item(item_id, values=(index, filename))

    def _on_image_press(self, event):
        """在图片行上按下左键：选中它，并记下拖动起点。"""
        row_id = self.image_tree.identify_row(event.y)
        if not row_id:
            self._drag_image_id = None
            return None

        self.image_tree.selection_set(row_id)
        self.image_tree.focus(row_id)
        self._drag_image_id = row_id
        self._drag_started = False
        self._drag_press_y = event.y
        return None

    def _on_image_motion(self, event):
        """
        按住左键上下移动：把当前行挪到鼠标所在行，其它行自动让位。

        鼠标移动超过 5 像素才算拖动，避免普通点击时误触发。
        拖动中的行加「dragging」标签，显示浅蓝色背景。
        """
        image_id = self._drag_image_id
        if not image_id or not self.image_tree.exists(image_id):
            return None

        if not self._drag_started:
            if abs(event.y - self._drag_press_y) < 5:
                return None
            self._drag_started = True
            self.image_tree.item(image_id, tags=('dragging',))
            self.image_tree.selection_set(image_id)

        target_id = self.image_tree.identify_row(event.y)
        if not target_id or target_id == image_id:
            return 'break'

        target_index = self.image_tree.index(target_id)
        bbox = self.image_tree.bbox(target_id)
        if bbox and event.y > bbox[1] + bbox[3] // 2:
            # 落在目标行的下半部分，就插到它后面
            target_index += 1

        # Treeview.move 的 index 是「移走当前行之后」的位置：
        # 往下拖时目标位置会往前挪一格，这里先减掉，避免差一位。
        source_index = self.image_tree.index(image_id)
        if target_index > source_index:
            target_index -= 1

        self.image_tree.move(image_id, '', target_index)
        self._renumber_image_rows()
        return 'break'

    def _on_image_release(self, event):
        """
        松开左键：如果刚才真的拖动过，就把表格里的新顺序写进数据库。

        写完重新读一遍数据库并刷新，确保界面显示的就是真实保存的顺序；
        最后保持被拖动的那张图处于选中状态。
        """
        image_id = self._drag_image_id
        was_dragging = self._drag_started
        self._drag_image_id = None
        self._drag_started = False

        if not image_id or not self.image_tree.exists(image_id):
            return None

        self.image_tree.item(image_id, tags=())
        if not was_dragging:
            return None

        ordered_ids = []
        for item_id in self.image_tree.get_children():
            try:
                ordered_ids.append(int(item_id))
            except (TypeError, ValueError):
                # 正常情况下不会发生；真遇到就放弃这次拖动
                self._refresh_images()
                return None

        try:
            db.reorder_node_images(self.node_id, ordered_ids)
        except Exception as error:
            messagebox.showerror(
                '排序失败',
                '图片顺序没有保存：\n%s' % error,
                parent=self.window,
            )
            self._refresh_images()
            return None

        self._refresh_images()
        item_id = str(image_id)
        if self.image_tree.exists(item_id):
            self.image_tree.selection_set(item_id)
            self.image_tree.focus(item_id)
            self.image_tree.see(item_id)
        return None

    def _on_image_right_click(self, event):
        """右键图片表格：点在图片上弹「删除/重命名」，点在空白处弹「添加」。"""
        row_id = self.image_tree.identify_row(event.y)
        if not row_id:
            self._show_image_menu(self.image_blank_menu, event)
            return 'break'

        self.image_tree.selection_set(row_id)
        self.image_tree.focus(row_id)
        self._show_image_menu(self.image_row_menu, event)
        return 'break'

    def _on_images_blank_right_click(self, event):
        """右键图片表格外面的空白边框：也当作「空白处」，弹出添加图片。"""
        self._show_image_menu(self.image_blank_menu, event)
        return 'break'

    def _show_image_menu(self, menu, event):
        """在鼠标位置弹出图片右键菜单。"""
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------
    # 把三种添加方式都接到同一个入口
    # ------------------------------------------------------------------

    def _register_drop_targets(self):
        """
        把窗口里面每一个控件都登记成拖放目标，并接上 Ctrl+V。

        拖放登记：这样不管文件落在表格上、文字框上还是空白处，都能接住。
        Ctrl+V 必须绑在控件自己身上（不能只绑在窗口上），
        因为 Tk 会先执行控件自带的粘贴，再轮到窗口；
        绑在控件上并返回「break」才能真正拦住文件路径被粘进文字里。
        """
        stack = [self.window]
        while stack:
            widget = stack.pop()
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', self._on_drop)
            except Exception:
                # 个别控件不支持拖放就跳过，不影响其它控件
                pass

            if widget is not self.window:
                # 不在窗口本身上绑，避免同一次 Ctrl+V 被处理两遍
                widget.bind('<Control-v>', self._on_paste)
                widget.bind('<Control-V>', self._on_paste)

            stack.extend(widget.winfo_children())

    def _on_drop(self, event):
        """拖放事件：拿到文件路径列表，交给统一的加入图片方法。"""
        if self.node_id is None:
            messagebox.showinfo(
                '提示',
                '请先填写标题并点「保存」，再给节点添加笔记图片。',
                parent=self.window,
            )
            return event.action

        try:
            paths = list(self.window.tk.splitlist(event.data))
        except Exception:
            paths = [event.data] if event.data else []

        self._add_images(paths)
        return event.action

    def _on_paste(self, event=None):
        """
        按 Ctrl+V 时调用。

        - 剪贴板里是图片文件：走统一的加入图片逻辑；
        - 剪贴板里是截图位图：明确提示先另存为文件；
        - 剪贴板里是普通文字：返回 None，让文本框照常粘贴文字。
        """
        paths = _clipboard_file_paths(self.window)

        if self.node_id is None:
            if paths or _clipboard_has_bitmap():
                messagebox.showinfo(
                    '提示',
                    '请先填写标题并点「保存」，再给节点添加笔记图片。',
                    parent=self.window,
                )
                return 'break'
            return None

        if paths:
            self._add_images(paths)
            return 'break'

        if _clipboard_has_bitmap():
            messagebox.showinfo(
                '提示',
                '截图请先另存为图片文件，再拖进来或粘贴文件。',
                parent=self.window,
            )
            return 'break'

        return None

    def _on_add_images(self):
        """右键空白处选「添加图片」：弹出可多选的文件选择框。"""
        pattern = ' '.join('*' + extension for extension in db.IMAGE_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            parent=self.window,
            title='选择笔记图片',
            filetypes=[
                ('图片文件', pattern),
                ('所有文件', '*.*'),
            ],
        )
        if paths:
            self._add_images(list(paths))

    def _add_images(self, paths):
        """
        统一的「加入图片」入口：拖放、Ctrl+V、右键菜单三条路都走这里。

        只接受 IMAGE_EXTENSIONS 里的扩展名；其它类型忽略并提示。
        每张图片按当前顺序排到最后，全部加完后刷新一次列表。
        """
        if self.node_id is None:
            messagebox.showinfo(
                '提示',
                '请先填写标题并点「保存」，再给节点添加笔记图片。',
                parent=self.window,
            )
            return

        if not paths:
            return

        valid_paths = []
        ignored_names = []
        for path in paths:
            text = str(path)
            extension = os.path.splitext(text)[1].lower()
            if os.path.isfile(text) and extension in db.IMAGE_EXTENSIONS:
                valid_paths.append(text)
            else:
                ignored_names.append(os.path.basename(text) or text)

        failures = []
        for path in valid_paths:
            try:
                db.store_image_file(self.node_id, path)
            except Exception as error:
                failures.append('%s：%s' % (os.path.basename(path), error))

        if valid_paths:
            self._refresh_images()

        if ignored_names:
            message = (
                '下面这些文件不是支持的图片类型，已经忽略：\n'
                + '\n'.join(ignored_names)
                + '\n\n只支持 png、jpg、jpeg、bmp、gif、webp 这几种图片。'
            )
            messagebox.showwarning('提示', message, parent=self.window)

        if failures:
            message = (
                '下面这些图片没有加进来：\n'
                + '\n'.join(failures)
            )
            messagebox.showerror('添加图片失败', message, parent=self.window)

    # ------------------------------------------------------------------
    # 图片的选中、打开、删除、重命名、拖动排序
    # ------------------------------------------------------------------

    def _selected_image(self):
        """返回表格里当前选中的图片记录，没选中返回 None。"""
        selection = self.image_tree.selection()
        if not selection:
            return None

        try:
            image_id = int(selection[0])
        except (TypeError, ValueError):
            return None

        for image in self.images:
            if image['id'] == image_id:
                return image
        return db.get_node_image(image_id)

    def _on_image_double_click(self, event):
        """双击某一行：用系统默认程序打开原图；文件没了就提示清记录。"""
        row_id = self.image_tree.identify_row(event.y)
        if not row_id:
            return

        self.image_tree.selection_set(row_id)
        image = self._selected_image()
        if image is None:
            return

        path = db.image_absolute_path(image['stored_path'])
        if not os.path.isfile(path):
            messagebox.showwarning(
                '文件已丢失',
                '这张图片的文件已经不存在：\n%s\n\n'
                '可以用「删除图片」清掉这条记录。' % image['filename'],
                parent=self.window,
            )
            return

        try:
            os.startfile(path)
        except OSError as error:
            messagebox.showerror(
                '打不开图片',
                '无法打开这张图片：\n%s\n\n%s' % (path, error),
                parent=self.window,
            )

    def _on_delete_image(self):
        """删一张图：先二次确认，再删数据库记录和磁盘上的副本。"""
        image = self._selected_image()
        if image is None:
            messagebox.showinfo(
                '提示', '请先在列表里选中一张图片。', parent=self.window
            )
            return

        if not messagebox.askyesno(
            '确认删除',
            '确定要删除图片「%s」吗？\n'
            '数据库记录和附件文件夹里的这份文件都会删除。' % image['filename'],
            parent=self.window,
        ):
            return

        stored_path = db.delete_node_image(image['id'])
        if stored_path:
            path = db.image_absolute_path(stored_path)
            try:
                os.remove(path)
            except FileNotFoundError:
                # 文件本来就不在了，记录已经删掉，不用再打扰用户
                pass
            except OSError as error:
                messagebox.showwarning(
                    '提示',
                    '数据库记录已经删除，但磁盘文件没能删掉：\n%s\n\n%s'
                    % (path, error),
                    parent=self.window,
                )

        self._refresh_images()

    def _on_rename_image(self):
        """
        右键「重命名」：改文件名，磁盘上的副本和数据库记录一起改。

        只允许改名字，不允许改文件夹；不写扩展名时自动沿用原扩展名；
        如果新名字和文件夹里已有文件重名，明确报错，绝不覆盖。
        """
        image = self._selected_image()
        if image is None:
            messagebox.showinfo(
                '提示', '请先在列表里选中一张图片。', parent=self.window
            )
            return

        new_name = simpledialog.askstring(
            '重命名图片',
            '请输入新的文件名（含扩展名）：',
            initialvalue=image['filename'],
            parent=self.window,
        )
        if new_name is None:
            # 用户点了「取消」
            return

        image_id = image['id']
        try:
            db.rename_node_image_file(image_id, new_name)
        except FileNotFoundError:
            messagebox.showwarning(
                '文件已丢失',
                '这张图片的文件已经不存在，不能重命名：\n%s\n\n'
                '可以用「删除图片」清掉这条记录。' % image['filename'],
                parent=self.window,
            )
            return
        except (ValueError, FileExistsError) as error:
            messagebox.showwarning(
                '重命名失败', str(error), parent=self.window
            )
            return
        except OSError as error:
            messagebox.showerror(
                '重命名失败',
                '改文件名时出错：\n%s' % error,
                parent=self.window,
            )
            return

        # 重新读数据库，保证显示的就是磁盘上真实的文件名
        self._refresh_images()
        item_id = str(image_id)
        if self.image_tree.exists(item_id):
            self.image_tree.selection_set(item_id)
            self.image_tree.focus(item_id)
            self.image_tree.see(item_id)

    # ------------------------------------------------------------------
    # 保存、删除节点、关闭
    # ------------------------------------------------------------------

    def _current_values(self):
        """取当前输入框里的标题和文字（去掉 Text 末尾自动多的那个换行）。"""
        return (
            self.title_var.get(),
            self.content_text.get('1.0', 'end-1c'),
        )

    def _is_dirty(self):
        """内容与刚打开时不一样，就认为「改过」。"""
        return self._current_values() != self._original

    def _notify_closed(self):
        """
        窗口真正关闭前，通知主界面刷新列表。

        只调用一次；调用完就把回调清空，避免同一个窗口重复刷新。
        """
        callback = self.on_closed
        if callback is None:
            return
        self.on_closed = None
        callback(self)

    def _on_save(self):
        """点「保存」：标题不能为空，然后写入数据库并关闭窗口。"""
        title = self.title_var.get().strip()
        content = self.content_text.get('1.0', 'end-1c')
        if not title:
            messagebox.showwarning('提示', '标题不能为空。', parent=self.window)
            self.title_entry.focus_set()
            return
        if self.node_id is None:
            self.node_id = db.create_node(self.subject_id, title, content)
        else:
            db.update_node(self.node_id, title, content)
        self.saved = True
        self._notify_closed()
        self.window.destroy()

    def _on_delete(self):
        """
        点「删除本节点」：二次确认后真的删掉，并告诉调用方已删除。

        图片记录和附件文件夹由 db.delete_node 一起清理，
        这里不再额外弹任何关于图片的提示，一次确认就够。
        """
        if self.node_id is None:
            return
        node = db.get_node(self.node_id)
        if node is None:
            # 已经被别处删掉了，直接关窗
            messagebox.showinfo('提示', '这个节点已经不存在了。', parent=self.window)
            self.deleted = True
            self._notify_closed()
            self.window.destroy()
            return
        if not messagebox.askyesno(
            '确认删除',
            '确定要删除节点「%s」吗？\n删除后无法恢复。' % node['title'],
            parent=self.window,
        ):
            return
        db.delete_node(self.node_id)
        self.deleted = True
        self._notify_closed()
        self.window.destroy()

    def _on_close(self):
        """点「关闭」或右上角叉：不保存；改过就问一句是否确定放弃改动。"""
        if self._is_dirty():
            if not messagebox.askyesno(
                '确认关闭', '改动未保存，确定关闭吗？', parent=self.window
            ):
                return
        self._notify_closed()
        self.window.destroy()


class CalendarDialog:
    """
    复习月历窗：看「哪天忘了什么」。

    窗口从上到下四块：
    1. 科目下拉框 + 可以直接输入（或点小箭头）的年、月；
    2. 周一到周日的表头 + 6 行 × 7 列的日期格子；
    3. 选中日期的标记列表（「科目名 › 节点标题」，按标记时间排序，多了可以拖滚动条）；
    4. 没有标记时，列表区域留空，中间显示一句「这天没有标记」。

    颜色规则：
    - 没标记的日期：白底 + 蓝字；
    - 有标记的日期：红底，深浅按「当前科目、当前月份里单日最大标记数」线性插值，
      标记越多越深；最大值只有 1 时也会直接是最深的红，绝不会和白色混淆；
    - 红底深时文字用白色，浅时用深灰，保证看得清；
    - 不属于当前月份的空格子留白且不能点。

    今天的格子用「加粗字体 + 更粗的边框」标出来，一眼能认出是哪天。
    整个窗口大小固定：点不同日期时只有列表内容变化，窗口不会跟着伸缩。
    """

    WEEKDAY_NAMES = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
    ROWS = 6
    COLS = 7

    # 颜色：没标记 = 白底蓝字；有标记 = 由浅红到深红
    PLAIN_BG = '#FFFFFF'
    PLAIN_FG = '#1A56C4'
    LIGHT_RED = (255, 178, 178)
    DEEP_RED = (150, 0, 0)
    DARK_TEXT = '#333333'
    WHITE_TEXT = '#FFFFFF'

    def __init__(self, parent, on_node_open=None, on_marks_changed=None):
        """
        parent：主窗口；
        on_node_open：双击某条标记时，用它打开节点详情（主界面的 open_node）；
        on_marks_changed：撤销标记后通知主界面刷新列表里的红色。
        """
        self.parent = parent
        self.on_node_open = on_node_open
        self.on_marks_changed = on_marks_changed

        self.subjects = []  # 科目列表（sqlite3.Row）
        self.subject_id = None  # 当前显示的科目 id
        self.marks_by_day = {}  # 当前科目当前月：{'2026-10-28': 2, …}
        self.cell_dates = {}  # (行, 列) → 'YYYY-MM-DD'，空格子为 None
        self._node_ids = {}  # 标记列表行 iid → 节点 id（双击打开用）

        today = dates.today_date()
        self.year = today.year
        self.month = today.month
        self.selected_date = dates.today_text()

        self.window = tk.Toplevel(parent)
        self.window.title('日历')
        self.window.protocol('WM_DELETE_WINDOW', self.window.destroy)

        self._build_ui()
        self.reload()
        # 固定大小：点不同日期时只有列表内容变化，窗口不许跟着伸缩
        _place_centered(self.window, parent, 760, 780)
        self.window.resizable(False, False)

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """摆好顶部工具条、月历格子、下方标记列表。"""
        body = ttk.Frame(self.window, padding=10)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        base_font = tkfont.nametofont('TkDefaultFont')
        self.cell_font = base_font.copy()
        self.cell_font.configure(size=11)
        self.today_font = base_font.copy()
        self.today_font.configure(size=11, weight='bold')
        title_font = base_font.copy()
        title_font.configure(size=12, weight='bold')

        # ---------------- 第一行：科目 + 年月 ----------------
        top = ttk.Frame(body)
        top.grid(row=0, column=0, sticky='ew')
        top.columnconfigure(2, weight=1)

        ttk.Label(top, text='科目：').grid(row=0, column=0, sticky='w')
        self.subject_combo = ttk.Combobox(
            top, state='readonly', width=18, values=[]
        )
        self.subject_combo.grid(row=0, column=1, sticky='w', padx=(0, 12))
        self.subject_combo.bind('<<ComboboxSelected>>', self._on_subject_selected)

        # 年月是可以直接敲的输入框（跨度大时不用连点几十下）：
        # 敲完按回车，或点一下别处（失去焦点）就跳到那个月；点右侧上下小箭头也行。
        # 顺带说明：因为没有「上一月 / 下一月」按钮，翻月全靠这两个输入框。
        self.month_frame = ttk.Frame(top)
        self.month_frame.grid(row=0, column=2, padx=10)
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.year_spin = tk.Spinbox(
            self.month_frame,
            from_=1900,
            to=2999,
            width=6,
            justify='center',
            font=title_font,
            textvariable=self.year_var,
            command=self._on_year_month_changed,
            relief='solid',
            bd=1,
        )
        self.year_spin.grid(row=0, column=0, sticky='e')
        ttk.Label(self.month_frame, text='年', font=title_font).grid(
            row=0, column=1, sticky='w', padx=(2, 8)
        )
        self.month_spin = tk.Spinbox(
            self.month_frame,
            from_=1,
            to=12,
            width=4,
            justify='center',
            font=title_font,
            textvariable=self.month_var,
            command=self._on_year_month_changed,
            relief='solid',
            bd=1,
        )
        self.month_spin.grid(row=0, column=2, sticky='w')
        ttk.Label(self.month_frame, text='月', font=title_font).grid(
            row=0, column=3, sticky='w', padx=(2, 0)
        )
        for spin in (self.year_spin, self.month_spin):
            # 敲完回车 / 点别处失去焦点，都当作「跳到这个月」
            spin.bind('<Return>', self._on_year_month_changed)
            spin.bind('<FocusOut>', self._on_year_month_changed)

        # 一个科目都没有时，这一行显示「还没有任何科目」
        self.info_var = tk.StringVar()
        self.info_label = ttk.Label(
            body, textvariable=self.info_var, anchor='w', foreground='#B00020'
        )
        self.info_label.grid(row=1, column=0, sticky='ew', pady=(6, 0))

        # ---------------- 第二行：周标题 ----------------
        weekday_frame = ttk.Frame(body)
        weekday_frame.grid(row=2, column=0, sticky='ew')
        for column, name in enumerate(self.WEEKDAY_NAMES):
            weekday_frame.columnconfigure(column, weight=1, uniform='day')
            ttk.Label(weekday_frame, text=name, anchor='center').grid(
                row=0, column=column, sticky='ew'
            )

        # ---------------- 第三行：6 × 7 日期格子 ----------------
        grid_frame = ttk.Frame(body, padding=(0, 4))
        grid_frame.grid(row=3, column=0, sticky='nsew')
        self.cells = []
        for row in range(self.ROWS):
            grid_frame.rowconfigure(row, weight=1, uniform='week')
            line = []
            for column in range(self.COLS):
                grid_frame.columnconfigure(column, weight=1, uniform='day')
                # 用 tk.Button（不是 ttk）才好按格子单独设底色和文字颜色
                button = tk.Button(
                    grid_frame,
                    text='',
                    width=5,
                    height=2,
                    relief='solid',
                    bd=1,
                    font=self.cell_font,
                    command=lambda: None,
                )
                button.grid(
                    row=row, column=column, sticky='nsew', padx=1, pady=1
                )
                line.append(button)
            self.cells.append(line)

        # ---------------- 第四行：当天的标记列表 ----------------
        list_frame = ttk.LabelFrame(body, text='当天标记', padding=6)
        list_frame.grid(row=4, column=0, sticky='nsew', pady=(8, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(1, weight=1)

        self.list_title_var = tk.StringVar()
        ttk.Label(
            list_frame, textvariable=self.list_title_var, anchor='w'
        ).grid(row=0, column=0, sticky='ew')

        inner = ttk.Frame(list_frame)
        inner.grid(row=1, column=0, sticky='nsew')
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(0, weight=1)

        self.mark_tree = ttk.Treeview(
            inner,
            columns=('label',),
            show='headings',
            selectmode='browse',
            height=8,
        )
        self.mark_tree.heading('label', text='科目名 › 节点标题')
        self.mark_tree.column(
            'label', anchor='w', width=560, minwidth=200, stretch=True
        )
        self.mark_tree.grid(row=0, column=0, sticky='nsew')
        self.mark_scroll = ttk.Scrollbar(
            inner, orient='vertical', command=self.mark_tree.yview
        )
        self.mark_scroll.grid(row=0, column=1, sticky='ns')
        self.mark_tree.configure(yscrollcommand=self.mark_scroll.set)
        self.mark_tree.bind('<Double-1>', self._on_mark_double_click)
        self.mark_tree.bind('<Button-3>', self._on_mark_right_click)
        # 标记很多时，除了拖右边滚动条，也可以直接滚鼠标滚轮
        self.mark_tree.bind('<MouseWheel>', self._on_mark_mousewheel)

        # 「这天没有标记」这类提示：用 place 盖在列表中间。
        # 用 place 而不是 grid，是因为 place 不参与窗口尺寸计算，
        # 显示 / 隐藏这句话都不会让下方的窗口变形。
        self.list_inner = inner
        self.list_empty = ttk.Label(
            inner, text='', anchor='center', justify='center'
        )

    # ------------------------------------------------------------------
    # 重新加载数据
    # ------------------------------------------------------------------

    def reload(self):
        """外部（主界面标了新的节点）调用：科目、当月标记、格子、列表全部按最新数据重画。"""
        self._load_subjects()
        self._load_marks()
        self._draw_month()
        self._fill_mark_list()

    def _load_subjects(self):
        """读科目下拉框；没有科目就禁用下拉框并显示一句提示。"""
        self.subjects = db.list_subjects()
        ids = [subject['id'] for subject in self.subjects]

        if not ids:
            self.subject_id = None
            self.subject_combo.configure(values=[], state='disabled')
            self.subject_combo.set('')
            self.info_var.set('还没有任何科目')
            return

        if self.subject_id not in ids:
            # 第一次打开（或原来的科目被删了）：按任务规则重新挑一个
            self.subject_id = db.default_calendar_subject_id()
        if self.subject_id not in ids:
            self.subject_id = ids[0]

        self.subject_combo.configure(
            values=[subject['name'] for subject in self.subjects],
            state='readonly',
        )
        self.subject_combo.set(self._subject_name(self.subject_id))
        self.info_var.set('')

    def _subject_name(self, subject_id):
        """按 id 找科目名，找不到返回空字符串。"""
        for subject in self.subjects:
            if subject['id'] == subject_id:
                return subject['name']
        return ''

    def _load_marks(self):
        """取「当前科目 + 当前显示月份」每天的标记数量。"""
        if self.subject_id is None:
            self.marks_by_day = {}
            return
        self.marks_by_day = db.count_marks_by_day(
            self.subject_id, self.year, self.month
        )

    # ------------------------------------------------------------------
    # 月历格子
    # ------------------------------------------------------------------

    def _draw_month(self):
        """按当前年月重画 42 个格子：日号、颜色、今天边框。"""
        self._sync_month_fields()
        first_weekday, days_in_month = calendar.monthrange(self.year, self.month)
        max_count = max(self.marks_by_day.values()) if self.marks_by_day else 0
        today_text = dates.today_text()

        for row in range(self.ROWS):
            for column in range(self.COLS):
                button = self.cells[row][column]
                index = row * self.COLS + column
                day = index - first_weekday + 1
                key = (row, column)

                if day < 1 or day > days_in_month:
                    # 不属于当前月份的空格子：留白、不可点
                    self.cell_dates[key] = None
                    button.configure(
                        text='',
                        state='disabled',
                        bg=self.PLAIN_BG,
                        fg=self.PLAIN_BG,
                        relief='flat',
                        bd=0,
                        font=self.cell_font,
                        command=lambda: None,
                    )
                    continue

                date_text = '%04d-%02d-%02d' % (self.year, self.month, day)
                self.cell_dates[key] = date_text
                count = self.marks_by_day.get(date_text, 0)
                background, foreground = self._cell_colors(count, max_count)
                is_today = date_text == today_text
                button.configure(
                    text=str(day),
                    state='normal',
                    bg=background,
                    fg=foreground,
                    activebackground=background,
                    activeforeground=foreground,
                    relief='solid',
                    bd=3 if is_today else 1,
                    font=self.today_font if is_today else self.cell_font,
                    command=lambda selected=date_text: self._on_day_click(selected),
                )

    def _cell_colors(self, count, max_count):
        """
        算一个格子的（底色, 文字色）。

        count 为 0：白底蓝字；
        count > 0：按 count / max_count 从浅红插值到深红，
        并用亮度决定文字用白色还是深灰。
        """
        if count <= 0 or max_count <= 0:
            return self.PLAIN_BG, self.PLAIN_FG

        ratio = float(count) / float(max_count)
        red = int(round(
            self.LIGHT_RED[0] + (self.DEEP_RED[0] - self.LIGHT_RED[0]) * ratio
        ))
        green = int(round(
            self.LIGHT_RED[1] + (self.DEEP_RED[1] - self.LIGHT_RED[1]) * ratio
        ))
        blue = int(round(
            self.LIGHT_RED[2] + (self.DEEP_RED[2] - self.LIGHT_RED[2]) * ratio
        ))
        # 人眼对绿色最敏感，用常见亮度公式判断该配白字还是深色字
        luminance = 0.299 * red + 0.587 * green + 0.114 * blue
        foreground = self.WHITE_TEXT if luminance < 150 else self.DARK_TEXT
        background = '#%02X%02X%02X' % (red, green, blue)
        return background, foreground

    # ------------------------------------------------------------------
    # 年月输入
    # ------------------------------------------------------------------

    def _sync_month_fields(self):
        """把「年」「月」两个输入框改回当前正在显示的月份。"""
        self.year_var.set(str(self.year))
        self.month_var.set(str(self.month))

    def _on_year_month_changed(self, event=None):
        """
        用户直接改了年或月（回车、失去焦点、点箭头）时跳到那个月。

        输入不合法（空、字母、超范围）就悄悄改回原来的年月，不弹窗打扰。
        """
        if not self.window.winfo_exists():
            return
        try:
            year = int(str(self.year_var.get()).strip())
            month = int(str(self.month_var.get()).strip())
        except (TypeError, ValueError):
            self._sync_month_fields()
            return

        # 夹到合理范围：年份 1900–2999，月份 1–12
        year = max(1900, min(2999, year))
        month = max(1, min(12, month))

        if year == self.year and month == self.month:
            # 没换月份（或输入被夹回原值）：只整理一下输入框里的字
            self._sync_month_fields()
            return

        self.year = year
        self.month = month

        # 跳月规则：跳到本月就选今天，否则选那个月 1 号
        today = dates.today_date()
        if today.year == year and today.month == month:
            self.selected_date = dates.today_text()
        else:
            self.selected_date = '%04d-%02d-01' % (year, month)

        self._load_marks()
        self._draw_month()
        self._fill_mark_list()

    def _on_subject_selected(self, event=None):
        """下拉框换了科目：重取这一科的当月标记并重画。"""
        index = self.subject_combo.current()
        if index < 0 or index >= len(self.subjects):
            return
        self.subject_id = self.subjects[index]['id']
        self._load_marks()
        self._draw_month()
        self._fill_mark_list()

    # ------------------------------------------------------------------
    # 点日期看当天
    # ------------------------------------------------------------------

    def _on_day_click(self, date_text):
        """点某个格子：下方列出那天这一科被标记的节点。"""
        self.selected_date = date_text
        self._fill_mark_list()

    def _fill_mark_list(self):
        """按「当前科目 + 选中日期」重新填下方列表。"""
        self.mark_tree.delete(*self.mark_tree.get_children())
        self._node_ids = {}

        if self.subject_id is None:
            self.list_title_var.set('还没有任何科目')
            self._show_list_empty('还没有任何科目')
            return

        marks = db.list_marks_of_date(self.subject_id, self.selected_date)
        self.list_title_var.set(
            '%s 的标记（共 %d 条）' % (self.selected_date, len(marks))
        )
        if not marks:
            self._show_list_empty('这天没有标记')
            return

        self._hide_list_empty()
        for mark in marks:
            item_id = str(mark['mark_id'])
            self.mark_tree.insert(
                '',
                'end',
                iid=item_id,
                values=('%s › %s' % (mark['subject_name'], mark['node_title']),),
            )
            self._node_ids[item_id] = mark['node_id']

    def _show_list_empty(self, text):
        """
        列表留空，并在中间显示一句提示。

        用 place 盖上去：place 不参与窗口尺寸计算，
        所以「显示这句话」和「收起这句话」都不会让窗口变大变小。
        """
        self.list_empty.configure(text=text)
        self.list_empty.place(relx=0.5, rely=0.5, anchor='center')

    def _hide_list_empty(self):
        """把中间那句提示收起来。"""
        self.list_empty.place_forget()

    def _on_mark_mousewheel(self, event):
        """在标记列表上滚鼠标滚轮：上下翻，标记很多时不用去拖滚动条。"""
        self.mark_tree.yview_scroll(int(-event.delta / 120), 'units')
        return 'break'

    def _selected_mark_node_id(self):
        """返回标记列表里选中那一行对应的节点 id，没选中返回 None。"""
        selection = self.mark_tree.selection()
        if not selection:
            return None
        return self._node_ids.get(selection[0])

    def _on_mark_double_click(self, event):
        """双击列表里的某条标记：打开那个节点的详情窗。"""
        row_id = self.mark_tree.identify_row(event.y)
        if not row_id:
            return
        node_id = self._node_ids.get(row_id)
        if node_id is None or self.on_node_open is None:
            return
        self.on_node_open(node_id)

    def _on_mark_right_click(self, event):
        """右键标记列表里的一行：弹出「撤销标记」。"""
        row_id = self.mark_tree.identify_row(event.y)
        if not row_id:
            return 'break'
        self.mark_tree.selection_set(row_id)
        self.mark_tree.focus(row_id)

        menu = tk.Menu(self.mark_tree, tearoff=0)
        menu.add_command(
            label='撤销标记',
            command=lambda rid=row_id: self.window.after_idle(
                lambda: self.undo_mark(rid)
            ),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def undo_mark(self, item_id):
        """
        撤销一条标记：二次确认后删除，日历格子和下方列表立刻重画。

        只删「这个节点在选中日期那一天」的记录，别的日期不受影响。
        """
        node_id = self._node_ids.get(item_id)
        if node_id is None:
            return
        values = self.mark_tree.item(item_id, 'values')
        label = values[0] if values else ''
        if not messagebox.askyesno(
            '确认撤销',
            '确定撤销「%s」在 %s 的标记吗？' % (label, self.selected_date),
            parent=self.window,
        ):
            return

        db.unmark_node(node_id, self.selected_date)
        self._load_marks()
        self._draw_month()
        self._fill_mark_list()

        # 主界面列表里的红色也要跟着消失
        if self.on_marks_changed is not None:
            self.on_marks_changed(node_id)


class HelpDialog:
    """
    使用帮助窗口（任务 04）。

    由主界面右上角的「?」按钮打开，同时只开一个（由 ui_main 控制）。
    - 文字只读，避免误改；但可以选中后复制；
    - 内容比窗口长，右侧有滚动条，也能用鼠标滚轮；
    - 点「关闭」或窗口右上角的 × 都能关掉。
    """

    def __init__(self, parent):
        self.parent = parent

        self.window = tk.Toplevel(parent)
        self.window.title('使用帮助')
        self.window.minsize(560, 420)
        self.window.protocol('WM_DELETE_WINDOW', self._on_close)
        # 跟着主窗口浮动，但不抓取输入（打开帮助时主界面仍然能操作）
        self.window.transient(parent)

        body = ttk.Frame(self.window, padding=12)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        text_frame = ttk.Frame(body)
        text_frame.grid(row=0, column=0, sticky='nsew')
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            wrap='word',
            padx=10,
            pady=8,
            relief='solid',
            borderwidth=1,
        )
        self.text.grid(row=0, column=0, sticky='nsew')

        scroll = ttk.Scrollbar(
            text_frame, orient='vertical', command=self.text.yview
        )
        scroll.grid(row=0, column=1, sticky='ns')
        self.text.configure(yscrollcommand=scroll.set)

        # 标题、小标题、正文、风险提示各用一种字体样式，便于快速扫读
        base_font = tkfont.nametofont('TkDefaultFont')
        title_font = base_font.copy()
        title_font.configure(size=13, weight='bold')
        heading_font = base_font.copy()
        heading_font.configure(size=11, weight='bold')
        body_font = base_font.copy()
        body_font.configure(size=10)
        self.text.tag_configure('title', font=title_font, spacing3=8)
        self.text.tag_configure(
            'heading', font=heading_font, spacing1=12, spacing3=4
        )
        self.text.tag_configure('body', font=body_font, spacing3=2)
        self.text.tag_configure('warn', font=body_font, foreground='#B00020')

        self._fill_text()

        # 填完内容再设为只读，防止用户误改帮助文字
        self.text.configure(state='disabled')

        bottom = ttk.Frame(body)
        bottom.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        ttk.Button(bottom, text='关闭', command=self._on_close).pack(side='right')

        _place_centered(self.window, parent, 700, 640)
        self.text.focus_set()

    def _fill_text(self):
        """把帮助内容分条写进文本框；六部分与 README.md 的说法保持一致。"""
        self.text.insert('end', '《知识节点》使用帮助\n', 'title')

        self.text.insert('end', '\n一、怎么建科目和知识节点\n', 'heading')
        self.text.insert(
            'end',
            '1. 在左边「科目」区的空白处点右键，选「新建科目」，输入科目名。\n'
            '2. 在右边节点列表的空白处点右键，选「新建节点」，填好标题和文字描述，点「保存」。\n'
            '3. 在科目或节点上点右键，可以重命名、删除；删除后无法恢复。\n'
            '4. 节点区上方的搜索框可以按标题或文字描述筛选当前科目的节点。\n',
            'body',
        )

        self.text.insert('end', '\n二、怎么往节点里加笔记图片\n', 'heading')
        self.text.insert(
            'end',
            '1. 双击节点打开详情窗，下面「笔记图片」区任选一种方式添加：\n'
            '   · 点「添加图片」按钮，在弹出的窗口里选图片文件；\n'
            '   · 把图片文件从资源管理器直接拖进详情窗；\n'
            '   · 在资源管理器里复制图片文件，回到详情窗按 Ctrl+V。\n'
            '2. 支持 png、jpg、jpeg、bmp、gif、webp。图片会复制一份到 data 目录，'
            '原图以后删掉也不影响。\n'
            '3. 截屏得到的位图不能直接按 Ctrl+V 粘贴：请先在画图等软件里'
            '另存为图片文件，再拖进来或粘贴文件。\n'
            '4. 在图片行上右键可以删除、重命名；按住图片行上下拖动可以调整顺序；'
            '双击图片会用 Windows 照片打开。\n',
            'body',
        )

        self.text.insert('end', '\n三、怎么标记「忘了」、当天为什么会变红置顶\n', 'heading')
        self.text.insert(
            'end',
            '1. 在节点上点右键，选「忘记了」，就记下「今天忘了这个节点」。\n'
            '2. 在日常模式下，当天被标记过的节点，整行会变成红色，并且排到列表最上面。\n'
            '3. 这里说的「今天」以凌晨 4 点为界：凌晨 0 点到 4 点之间算前一天。\n'
            '4. 同一天重复标记只算一次。已经标过的节点，右键菜单里的「忘记了」会变灰；'
            '想取消就选「没忘记」，只撤销今天这一条。\n'
            '5. 以前日期的标记会一直保留，并累计到「忘过次数」里。\n',
            'body',
        )

        self.text.insert('end', '\n四、日历怎么看、颜色深浅是什么意思、怎么撤销标记\n', 'heading')
        self.text.insert(
            'end',
            '1. 点顶部的「日历」按钮打开月历；年份和月份可以直接输入，也能点旁边的小箭头。\n'
            '2. 格子的红色越深，表示这个科目那一天忘记的节点越多；'
            '没有标记的日期是白底蓝字。\n'
            '3. 点某一天，下面的列表会显示当天标记过的节点；双击一条可以打开节点详情。\n'
            '4. 在下面的列表里右键选「撤销标记」，就能删掉那一天的标记；'
            '只影响选中的那一天，别的日期不动。\n',
            'body',
        )

        self.text.insert('end', '\n五、「按忘过次数排序」怎么用\n', 'heading')
        self.text.insert(
            'end',
            '1. 搜索框右边的「按忘过次数排序」默认不勾选，平时按「最近打开时间」排序。\n'
            '2. 勾上以后：忘过次数多的排前面；次数相同的，最近标记日期新的排前面；'
            '从没标记过的排最后。\n'
            '3. 勾上以后，当天标记的节点仍然是红色，但不再置顶，否则次数排序就不准了。\n'
            '4. 取消勾选就恢复原来的排序和置顶。切换立即生效，不用重启程序。\n'
            '5. 搜索框里的关键词在两种排序下都有效，筛选出来的结果照样按当前方式排序。\n'
            '6. 列表里的「忘过次数」和「最近标记」两列，统计的是这个节点从创建以来'
            '所有日期的标记；没标记过时显示「0 次」和「—」。\n',
            'body',
        )

        self.text.insert('end', '\n六、数据在哪个文件夹、怎么备份（重要）\n', 'heading')
        self.text.insert(
            'end',
            '1. 所有数据都在这个文件夹：\n'
            '   ' + db.DATA_DIR + '\n'
            '2. 其中 knowledge.db 是数据库（科目、节点、标记都在里面），'
            'attachments 文件夹里是笔记图片。\n'
            '3. 本软件不做自动备份，也没有备份按钮。请偶尔手动复制一份 data 文件夹，'
            '这是唯一可靠的数据保障。\n'
            '4. 换电脑、重装系统或清理磁盘前，先把整个 data 文件夹复制到 U 盘或网盘；'
            '恢复时把它放回原来的位置即可。\n',
            'body',
        )
        self.text.insert(
            'end',
            '\n风险提示：数据只保存在这台电脑的 data 文件夹里，删掉或损坏都无法找回。'
            '请养成偶尔手动复制一份 data 文件夹的习惯。\n',
            'warn',
        )

    def _on_close(self):
        """关闭帮助窗口（主界面那边下次点「?」会重新创建）。"""
        self.window.destroy()
