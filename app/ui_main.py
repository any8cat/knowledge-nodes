# -*- coding: utf-8 -*-
"""
app/ui_main.py —— 主窗口

职责：
1. 左侧科目区：科目列表 + 右键菜单（空白处新建科目，科目上改名或删除）；
2. 右侧节点区：顶部「日历」「?」按钮 + 搜索框 +「排序」菜单 +
   节点表格（ttk.Treeview）；表格空白处右键新建节点；节点上右键
   「忘记了 / 没忘记 / 打开 / 重命名 / 删除」；
3. 把用户操作接到 app\\db.py 的增删改查函数上，并在操作后刷新界面。

关于复习标记与统计（任务 03、04）：
- 节点右键选「忘记了」＝记下「逻辑今天忘了它」；选「没忘记」＝撤销今天的标记；
- 节点表格有三列：标题、忘过次数、最近标记日期，统计由 db.list_nodes 一条
  SQL 聚合出来，本文件只负责显示；
- 排序由搜索框右侧的「排序：…」菜单选择：
  「按最近浏览时间」「按忘记次数」「按最近忘记时间」，每种都能再选升序或降序；
- 逻辑今天被标记过的节点，无论选哪种排序都**显示红色**；
- 只有「按最近浏览时间 + 降序」这个默认日常模式才**置顶**；其他排序和升序都不置顶，
  否则排序结果就被置顶规则打乱了；
- 红色由数据库算出的 is_marked_today 决定，本文件只照着打 tag，
  不在这里挪行、也不缓存标记状态；
- 标记和撤销都不弹提示、也不写状态栏：列表里变红（或红色消失）本身就是反馈。

说明：
- 节点表格用 ttk.Treeview（不是 Listbox）；有笔记图片的节点，标题后面会显示「[3 图]」；
- 节点顺序完全由数据库查询决定（三种排序共用 db._fetch_nodes 的一条 SQL），
  本文件不做任何排序；
- 「?」按钮打开只读、可滚动的帮助窗（HelpDialog，在 ui_dialogs.py 里）；
- 本文件不写 SQL，也不直接弹节点详情窗、日历窗、帮助窗的界面，
  那些分别在 db.py 与 ui_dialogs.py 里。
"""

import tkinter as tk
import tkinter.font as tkfont
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

import db
import dates
from ui_dialogs import CalendarDialog, HelpDialog, NodeDialog, SubjectDialog

# 逻辑今天被标记过的节点：红色加粗（tag 名，与 refresh_nodes 里用的保持一致）
MARKED_TAG = 'marked_today'
MARKED_COLOR = '#C00000'


class MainWindow:
    """主窗口的全部界面与交互。"""

    def __init__(self, root):
        self.root = root
        self.current_subject_id = None  # 当前选中的科目 id；没有则为 None
        self.subjects = []  # 当前科目列表（sqlite3.Row 的列表）
        self.keyword_var = tk.StringVar()  # 搜索框里的关键词
        # 排序方式：默认「按最近浏览时间 + 降序」，保持原来的日常排序
        self.sort_mode_var = tk.StringVar(value=db.SORT_VIEWED)
        self.sort_order_var = tk.StringVar(value='desc')  # desc=降序，asc=升序
        self.calendar_dialog = None  # 日历窗口（同时只开一个）
        self.help_dialog = None  # 帮助窗口（同时只开一个）

        self._build_ui()
        self._bind_events()
        self.load_subjects()

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """按「左科目、右节点」的布局摆好所有控件。"""
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, minsize=250)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # ---------------- 左侧：科目区 ----------------
        left = ttk.LabelFrame(outer, text='科目', padding=8)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        subject_list_frame = ttk.Frame(left)
        subject_list_frame.grid(row=0, column=0, sticky='nsew')
        subject_list_frame.columnconfigure(0, weight=1)
        subject_list_frame.rowconfigure(0, weight=1)

        self.subject_list = tk.Listbox(
            subject_list_frame, exportselection=False, activestyle='dotbox'
        )
        self.subject_list.grid(row=0, column=0, sticky='nsew')
        subject_scroll = ttk.Scrollbar(
            subject_list_frame, orient='vertical', command=self.subject_list.yview
        )
        subject_scroll.grid(row=0, column=1, sticky='ns')
        self.subject_list.configure(yscrollcommand=subject_scroll.set)

        # ---------------- 右侧：节点区 ----------------
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        # 第一行：工具行（日历按钮和帮助按钮都放在最右边）
        button_frame = ttk.Frame(right)
        button_frame.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        button_frame.columnconfigure(0, weight=1)

        self.calendar_button = ttk.Button(
            button_frame, text='日历', command=self.open_calendar
        )
        self.calendar_button.grid(row=0, column=1, sticky='e')

        # 「?」帮助按钮：放在最右边，点开一个独立的使用说明小窗
        self.help_button = ttk.Button(
            button_frame, text='?', width=3, command=self.open_help
        )
        self.help_button.grid(row=0, column=2, sticky='e', padx=(8, 0))

        # 第二行：搜索框 + 排序菜单（默认「最近浏览 + 降序」）
        search_frame = ttk.Frame(right)
        search_frame.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text='搜索：').grid(row=0, column=0, sticky='w')
        self.search_entry = ttk.Entry(search_frame, textvariable=self.keyword_var)
        self.search_entry.grid(row=0, column=1, sticky='ew', padx=(4, 0))

        # 排序菜单按钮：点一下弹出菜单，菜单里选「排序字段」和「升序/降序」。
        # 用 tk.Menu 是为了让外观接近系统菜单（带勾选标记），不在主界面堆一排单选按钮。
        self.sort_button = ttk.Menubutton(search_frame, text='排序：最近浏览 ↓', width=18)
        self.sort_menu = tk.Menu(self.sort_button, tearoff=False)
        # 这些文字也用来估算菜单宽度，保证菜单不会伸出屏幕（见 _show_sort_menu）
        self._sort_menu_labels = [
            '按最近浏览时间',
            '按忘记次数',
            '按最近忘记时间',
            '降序',
            '升序',
        ]
        self.sort_menu.add_radiobutton(
            label=self._sort_menu_labels[0],
            variable=self.sort_mode_var,
            value=db.SORT_VIEWED,
            command=self._on_sort_mode_changed,
        )
        self.sort_menu.add_radiobutton(
            label=self._sort_menu_labels[1],
            variable=self.sort_mode_var,
            value=db.SORT_MARKS,
            command=self._on_sort_mode_changed,
        )
        self.sort_menu.add_radiobutton(
            label=self._sort_menu_labels[2],
            variable=self.sort_mode_var,
            value=db.SORT_LAST_MARK,
            command=self._on_sort_mode_changed,
        )
        self.sort_menu.add_separator()
        self.sort_menu.add_radiobutton(
            label=self._sort_menu_labels[3],
            variable=self.sort_order_var,
            value='desc',
            command=self._on_sort_mode_changed,
        )
        self.sort_menu.add_radiobutton(
            label=self._sort_menu_labels[4],
            variable=self.sort_order_var,
            value='asc',
            command=self._on_sort_mode_changed,
        )
        self.sort_button.configure(menu=self.sort_menu)
        self.sort_button.grid(row=0, column=2, sticky='e', padx=(10, 0))
        # 自己算菜单的弹出位置：让菜单右边缘和按钮右边缘对齐。
        # 如果直接用 Menubutton 默认的弹出方式，按钮又靠在窗口右边，
        # 菜单会往右伸出屏幕，后面的字就被截掉了。
        self.sort_button.bind('<Button-1>', self._show_sort_menu)
        self.sort_button.bind('<space>', self._show_sort_menu)
        self._update_sort_button_text()

        # 第三行：节点表格
        tree_frame = ttk.Frame(right)
        tree_frame.grid(row=2, column=0, sticky='nsew')
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # 三列：标题、忘过次数、最近标记日期。
        # 列宽按窗口 1100 计算：左侧科目区 250 + 边距后，右侧还能剩约 800 像素，
        # 三列合计 750，留出滚动条和边框的余量，所以「3 次」「2026-10-26」
        # 都能完整显示，不会被挤成省略号。
        self.tree = ttk.Treeview(
            tree_frame,
            columns=('title', 'mark_count', 'last_mark'),
            show='headings',
            selectmode='browse',
        )
        self.tree.heading('title', text='节点标题')
        self.tree.heading('mark_count', text='忘过次数')
        self.tree.heading('last_mark', text='最近标记')
        self.tree.column('title', anchor='w', width=500, minwidth=200, stretch=True)
        self.tree.column(
            'mark_count', anchor='center', width=110, minwidth=90, stretch=False
        )
        self.tree.column(
            'last_mark', anchor='center', width=130, minwidth=110, stretch=False
        )
        self.tree.grid(row=0, column=0, sticky='nsew')

        # 逻辑今天被标记过的行：红色加粗（字体在默认字体基础上加粗，不改变字号）
        bold_font = tkfont.nametofont('TkDefaultFont').copy()
        bold_font.configure(weight='bold')
        self.tree.tag_configure(
            MARKED_TAG, foreground=MARKED_COLOR, font=bold_font
        )

        self.tree_scroll = ttk.Scrollbar(
            tree_frame, orient='vertical', command=self.tree.yview
        )
        self.tree_scroll.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=self.tree_scroll.set)

        # 空列表时显示的提示文字（平时藏起来，需要时盖住表格区域）
        self.placeholder = ttk.Label(
            tree_frame, text='', anchor='center', justify='center'
        )

    def _bind_events(self):
        """把点选、右键菜单、双击、搜索这些鼠标和键盘操作接到处理函数上。"""
        self.subject_list.bind('<Button-1>', self._on_subject_left_click)
        self.subject_list.bind('<Button-3>', self._on_subject_right_click)
        self.subject_list.bind('<<ListboxSelect>>', self._on_subject_select)

        self.tree.bind('<Button-1>', self._on_tree_left_click)
        self.tree.bind('<Button-3>', self._on_tree_right_click)
        self.tree.bind('<Double-1>', self._on_tree_double_click)
        # 列表为空时表格被提示文字盖住，右键要绑在提示文字上才能弹出菜单
        self.placeholder.bind('<Button-3>', self._on_tree_right_click)

        self.keyword_var.trace_add('write', self._on_keyword_changed)

    # ------------------------------------------------------------------
    # 科目区
    # ------------------------------------------------------------------

    def load_subjects(self, select_id=None):
        """
        重新从数据库读取科目并刷新左侧列表。

        select_id：希望选中的科目 id（比如刚新建或改名的那个）；
        找不到时就尽量保留原来选中的科目，再不行就选第一个。
        """
        old_id = self.current_subject_id
        self.subjects = db.list_subjects()

        self.subject_list.delete(0, 'end')
        for subject in self.subjects:
            self.subject_list.insert('end', subject['name'])

        if not self.subjects:
            # 一个科目都没有：右侧清空并提示先建科目
            self.current_subject_id = None
            self.refresh_nodes()
            return

        target = None
        for wanted in (select_id, old_id):
            if wanted is None:
                continue
            for index, subject in enumerate(self.subjects):
                if subject['id'] == wanted:
                    target = index
                    break
            if target is not None:
                break
        if target is None:
            target = 0

        self.subject_list.selection_set(target)
        self.subject_list.activate(target)
        self.subject_list.see(target)
        self.current_subject_id = self.subjects[target]['id']
        self.refresh_nodes()

    def _selected_subject(self):
        """返回左侧当前选中的科目（sqlite3.Row），没选中返回 None。"""
        selection = self.subject_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(self.subjects):
            return None
        return self.subjects[index]

    def _on_subject_select(self, event=None):
        """用户点了左侧某个科目：右侧换成这一科的节点。"""
        subject = self._selected_subject()
        if subject is None:
            return
        self.current_subject_id = subject['id']
        self.refresh_nodes()

    def _subject_index_at(self, y):
        """
        按鼠标的纵坐标找「真正被点中」的科目。

        返回科目在 self.subjects 里的下标；如果点在条目之间的空白、
        或条目下方的空白处，则返回 None（不能算点中任何科目）。
        """
        if not self.subjects:
            return None
        index = self.subject_list.nearest(y)
        if index < 0 or index >= len(self.subjects):
            return None
        box = self.subject_list.bbox(index)
        if not box:
            return None
        top = box[1]
        height = box[3]
        if top <= y < top + height:
            return index
        return None

    def _on_subject_left_click(self, event):
        """
        左键点科目列表：只有真的点在某一项上，才让 Listbox 去选中它。

        默认的 Listbox 在点条目下方的大片空白时，会选中最后一个科目，
        这里用「break」拦掉这种点击，避免误触。
        """
        if self._subject_index_at(event.y) is None:
            return 'break'
        return None

    def _on_subject_right_click(self, event):
        """
        右键科目列表。

        - 点在空白处：弹出「新建科目」；
        - 点在某个科目上：先选中它，再弹出「重命名 / 删除」。
        """
        index = self._subject_index_at(event.y)
        if index is None:
            self._show_subject_menu(event, None)
            return 'break'

        self.subject_list.selection_clear(0, 'end')
        self.subject_list.selection_set(index)
        self.subject_list.activate(index)
        subject = self.subjects[index]
        self.current_subject_id = subject['id']
        self.refresh_nodes()
        self._show_subject_menu(event, subject)
        return 'break'

    def _show_subject_menu(self, event, subject=None):
        """在鼠标位置弹出科目右键菜单。"""
        menu = tk.Menu(self.subject_list, tearoff=0)
        if subject is None:
            menu.add_command(
                label='新建科目',
                command=lambda: self.root.after_idle(self.new_subject),
            )
        else:
            menu.add_command(
                label='重命名',
                command=lambda s=subject: self.root.after_idle(
                    lambda: self.rename_subject(s)
                ),
            )
            menu.add_command(
                label='删除',
                command=lambda s=subject: self.root.after_idle(
                    lambda: self.delete_subject(s)
                ),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def new_subject(self):
        """新建科目：由右键菜单的「新建科目」调用。"""
        dialog = SubjectDialog(self.root, mode='create')
        self.root.wait_window(dialog.window)
        if dialog.result_id is not None:
            self.load_subjects(select_id=dialog.result_id)

    def rename_subject(self, subject=None):
        """给科目改名；从右键菜单进来时直接传入该科目。"""
        if subject is None:
            subject = self._selected_subject()
        if subject is None:
            messagebox.showinfo(
                '提示', '请先在左边选中一个科目。', parent=self.root
            )
            return
        dialog = SubjectDialog(self.root, mode='rename', subject=subject)
        self.root.wait_window(dialog.window)
        if dialog.result_id is not None:
            self.load_subjects(select_id=dialog.result_id)

    def delete_subject(self, subject=None):
        """删除科目：二次确认后，连带删掉这一科的全部节点。"""
        if subject is None:
            subject = self._selected_subject()
        if subject is None:
            messagebox.showinfo(
                '提示', '请先在左边选中一个科目。', parent=self.root
            )
            return
        if not messagebox.askyesno(
            '确认删除',
            '确定要删除科目「%s」吗？\n它下面的所有节点也会一起删除，且无法恢复。'
            % subject['name'],
            parent=self.root,
        ):
            return
        db.delete_subject(subject['id'])
        # 这个科目没了，让 load_subjects 重新挑一个（没有科目就清空右边）
        self.current_subject_id = None
        self.load_subjects()

    # ------------------------------------------------------------------
    # 节点区
    # ------------------------------------------------------------------

    def refresh_nodes(self, select_id=None):
        """
        按「当前科目 + 当前搜索词 + 当前排序方式」重新读取节点并填满右侧表格。

        搜索与排序都交给 db.list_nodes 的同一个查询完成，这里不再排序。
        红色与置顶规则（重要）：
        - 逻辑今天标记过的行，无论选哪种排序都显示红色；
        - 只有「按最近浏览时间 + 降序」的默认日常模式才置顶；
        - 按次数、按最近忘记时间，以及任何升序，都只红不置顶，
          否则排序结果会被置顶规则打乱；
        结果为空时用提示文字代替表格。
        """
        keyword = self.keyword_var.get().strip()
        sort_mode = self.sort_mode_var.get()
        descending = self.sort_order_var.get() == 'desc'
        self.tree.delete(*self.tree.get_children())

        if self.current_subject_id is None:
            if not self.subjects:
                self._show_placeholder('请先新建一个科目')
            else:
                self._show_placeholder('请先在左边选中一个科目')
            return

        # 所有排序共用这一个函数、同一条 SQL，只由 sort_mode + descending 决定 ORDER BY；
        # 搜索关键词也一起传进去，保证「排序 + 搜索」仍然按当前方式排。
        nodes = db.list_nodes(
            self.current_subject_id,
            keyword,
            sort_mode=sort_mode,
            descending=descending,
        )

        if not nodes:
            if keyword:
                self._show_placeholder('没有匹配的节点')
            else:
                self._show_placeholder(
                    '这个科目下还没有节点，在下方空白处右键选「新建节点」添加。'
                )
            return

        self._show_tree()
        for node in nodes:
            # 有笔记图片的节点，在标题后面加「[N 图]」标记；没有图就只显示标题
            image_count = node['image_count']
            if image_count:
                title = '%s [%d 图]' % (node['title'], image_count)
            else:
                title = node['title']

            # 统计列：没标记过显示「0 次」和「—」，标记过显示「3 次」和日期
            mark_count = node['mark_count']
            count_text = '%d 次' % mark_count
            last_mark_text = node['last_mark_date'] or '—'

            # is_marked_today 由 SQL 算好：1 表示逻辑今天被标记过，整行变红。
            # 次数模式下它只影响颜色、不影响顺序（见 db._fetch_nodes 的 ORDER BY）。
            if node['is_marked_today']:
                tags = (MARKED_TAG,)
            else:
                tags = ()
            self.tree.insert(
                '',
                'end',
                iid=str(node['id']),
                values=(title, count_text, last_mark_text),
                tags=tags,
            )

        if select_id is not None:
            item = str(select_id)
            if self.tree.exists(item):
                self.tree.selection_set(item)
                self.tree.focus(item)
                self.tree.see(item)

    def _show_placeholder(self, text):
        """清空表格区域，改为居中显示一句提示。"""
        self.tree.grid_remove()
        self.tree_scroll.grid_remove()
        self.placeholder.configure(text=text)
        self.placeholder.grid(row=0, column=0, columnspan=2, sticky='nsew')

    def _show_tree(self):
        """恢复显示节点表格。"""
        self.placeholder.grid_remove()
        self.tree.grid()
        self.tree_scroll.grid()

    def _on_keyword_changed(self, *args):
        """搜索框内容一变就立刻重新筛选（各种排序方式下都生效）。"""
        self.refresh_nodes()

    def _show_sort_menu(self, event=None):
        """
        在按钮下方弹出排序菜单，并让菜单的右边缘贴着按钮的右边缘。

        这样做是为了防止主窗口靠屏幕右边时，菜单伸出屏幕、文字被截掉。
        返回 'break' 是为了拦住 Menubutton 自带的弹出动作，避免菜单弹两次。
        """
        self.sort_menu.update_idletasks()
        # 菜单还没显示时 winfo_reqwidth() 不可靠，改为按菜单字体量一下最长的文字，
        # 再加上勾选标记和左右内边距，估算菜单宽度。
        menu_font = tkfont.nametofont('TkDefaultFont')
        text_width = max(menu_font.measure(text) for text in self._sort_menu_labels)
        menu_width = text_width + 80
        # 五行菜单项 + 一条分隔线，按字体行高估算菜单高度
        menu_height = menu_font.metrics('linespace') * 7 + 16
        x = self.sort_button.winfo_rootx() + self.sort_button.winfo_width() - menu_width
        y = self.sort_button.winfo_rooty() + self.sort_button.winfo_height()
        screen_width = self.sort_button.winfo_screenwidth()
        screen_height = self.sort_button.winfo_screenheight()
        if x + menu_width > screen_width:
            x = screen_width - menu_width - 8
        if x < 8:
            x = 8
        if y + menu_height > screen_height:
            # 窗口靠屏幕下边时，菜单改为向上弹，避免下半截看不见
            y = self.sort_button.winfo_rooty() - menu_height
        if y < 8:
            y = 8
        try:
            self.sort_menu.tk_popup(x, y)
        finally:
            self.sort_menu.grab_release()
        return 'break'

    def _on_sort_mode_changed(self):
        """
        在排序菜单里换了排序字段或升/降序：立刻按新排序重画，不需要重启程序。

        三种字段：
        - 最近浏览：降序＝最近看过的在前；升序＝最久没看的在前；
        - 忘记次数：降序＝忘得多的在前；升序＝忘得少的在前；
        - 最近忘记：降序＝最近忘的在前；升序＝忘得最久的在前。
        不管选哪种，当天标记的节点仍然红色；只有「最近浏览 + 降序」才置顶。
        重画时尽量保持当前选中的节点，避免它从视野里跑丢。
        """
        selected_id = self._selected_node_id()
        self._update_sort_button_text()
        self.refresh_nodes(select_id=selected_id)

    def _update_sort_button_text(self):
        """把按钮文字更新成「排序：字段 ↑/↓」，让用户一眼看到当前排序。"""
        labels = {
            db.SORT_VIEWED: '最近浏览',
            db.SORT_MARKS: '忘记次数',
            db.SORT_LAST_MARK: '最近忘记',
        }
        mode_text = labels.get(self.sort_mode_var.get(), '最近浏览')
        arrow = '↓' if self.sort_order_var.get() == 'desc' else '↑'
        self.sort_button.configure(text='排序：%s %s' % (mode_text, arrow))

    def _selected_node_id(self):
        """返回右侧表格里当前选中的节点 id，没选中返回 None。"""
        selection = self.tree.selection()
        if not selection:
            return None
        return int(selection[0])

    def _node_id_at(self, y):
        """
        按鼠标纵坐标找「真正被点中」的节点行。

        点在表头、行与行之间的空白，或所有节点下方的空白处时，返回 None，
        这样右键和左键都能区分「点在节点上」和「点在空白处」。
        """
        row_id = self.tree.identify_row(y)
        if not row_id:
            return None
        return int(row_id)

    def _on_tree_left_click(self, event):
        """
        左键点节点表格：只有点在节点行上才让表格选中它。

        点表格下方空白时保持原来的选中项不变，避免误触。
        """
        if self._node_id_at(event.y) is None:
            return 'break'
        return None

    def _on_tree_right_click(self, event):
        """
        右键节点表格。

        - 点在空白处：弹出「新建节点」；
        - 点在某个节点上：先选中它，再弹出
          「忘记了 / 没忘记 / 打开 / 重命名 / 删除」。
        """
        node_id = self._node_id_at(event.y)
        if node_id is None:
            self._show_node_menu(event, None)
            return 'break'

        item = str(node_id)
        self.tree.selection_set(item)
        self.tree.focus(item)
        self._show_node_menu(event, node_id)
        return 'break'

    def _show_node_menu(self, event, node_id=None):
        """在鼠标位置弹出节点右键菜单。"""
        menu = tk.Menu(self.tree, tearoff=0)
        if node_id is None:
            menu.add_command(
                label='新建节点',
                command=lambda: self.root.after_idle(self.new_node),
            )
        else:
            # 这一行现在是不是「逻辑今天标过」的：决定「忘记了」「没忘记」哪项可点。
            # 已经标过的再点「忘记了」没有意义，没标过的再点「没忘记」也没有意义，
            # 所以直接把用不上的那项置灰，比点了没反应更好懂。
            is_marked = MARKED_TAG in self.tree.item(str(node_id), 'tags')

            menu.add_command(
                label='忘记了',
                state='normal' if not is_marked else 'disabled',
                command=lambda nid=node_id: self.root.after_idle(
                    lambda: self.mark_node(nid)
                ),
            )
            menu.add_command(
                label='没忘记',
                state='normal' if is_marked else 'disabled',
                command=lambda nid=node_id: self.root.after_idle(
                    lambda: self.unmark_node(nid)
                ),
            )
            menu.add_separator()
            menu.add_command(
                label='打开',
                command=lambda nid=node_id: self.root.after_idle(
                    lambda: self.open_node(nid)
                ),
            )
            menu.add_command(
                label='重命名',
                command=lambda nid=node_id: self.root.after_idle(
                    lambda: self.rename_node(nid)
                ),
            )
            menu.add_command(
                label='删除',
                command=lambda nid=node_id: self.root.after_idle(
                    lambda: self.delete_node(nid)
                ),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_tree_double_click(self, event):
        """双击表格里的某一行：打开该节点的详情窗。"""
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        self.open_node(int(row_id))

    def open_selected_node(self):
        """打开当前选中的节点（保留给代码调用，界面入口在右键菜单里）。"""
        node_id = self._selected_node_id()
        if node_id is None:
            messagebox.showinfo(
                '提示', '请先在右边的列表里选中一个节点。', parent=self.root
            )
            return
        self.open_node(node_id)

    def open_node(self, node_id):
        """打开节点详情窗：先把最近打开时间记为现在，再显示窗口。"""
        node = db.get_node(node_id)
        if node is None:
            messagebox.showwarning(
                '提示', '这个节点已经不存在了。', parent=self.root
            )
            self.refresh_nodes()
            return

        # 打开即算「看过」，这样关掉详情窗后它就排到列表最上面
        db.touch_node_viewed(node_id)

        # 不调用 wait_window，窗口打开后主界面马上就能继续点，
        # 还可以同时打开别的科目、别的节点详情窗。
        NodeDialog(
            self.root,
            node=node,
            on_closed=self._on_node_dialog_closed,
        )

    def _on_node_dialog_closed(self, dialog):
        """节点详情窗关闭后刷新列表：删了节点就重查，否则尽量保持选中。"""
        if dialog.deleted:
            self.refresh_nodes()
        else:
            self.refresh_nodes(select_id=dialog.node_id)

    def rename_node(self, node_id):
        """给节点改标题：只改标题，文字描述原样保留。"""
        node = db.get_node(node_id)
        if node is None:
            messagebox.showwarning(
                '提示', '这个节点已经不存在了。', parent=self.root
            )
            self.refresh_nodes()
            return

        new_title = simpledialog.askstring(
            '重命名节点',
            '请输入新的节点标题：',
            initialvalue=node['title'],
            parent=self.root,
        )
        if new_title is None:
            # 用户点了「取消」
            return
        new_title = new_title.strip()
        if not new_title:
            messagebox.showwarning(
                '提示', '节点标题不能为空。', parent=self.root
            )
            return
        if new_title == node['title']:
            return

        db.update_node(node_id, new_title, node['content'])
        self.refresh_nodes(select_id=node_id)

    def delete_node(self, node_id):
        """二次确认后删除指定节点。"""
        node = db.get_node(node_id)
        if node is None:
            messagebox.showwarning(
                '提示', '这个节点已经不存在了。', parent=self.root
            )
            self.refresh_nodes()
            return
        if not messagebox.askyesno(
            '确认删除',
            '确定要删除节点「%s」吗？\n删除后无法恢复。' % node['title'],
            parent=self.root,
        ):
            return
        db.delete_node(node_id)
        self.refresh_nodes()

    def new_node(self):
        """在当前选中的科目下建节点（右键菜单的「新建节点」调用）。"""
        if self.current_subject_id is None:
            if not self.subjects:
                messagebox.showinfo(
                    '提示', '请先新建一个科目。', parent=self.root
                )
            else:
                messagebox.showinfo(
                    '提示', '请先在左边选中一个科目。', parent=self.root
                )
            return
        NodeDialog(
            self.root,
            node=None,
            subject_id=self.current_subject_id,
            on_closed=self._on_new_node_dialog_closed,
        )

    def _on_new_node_dialog_closed(self, dialog):
        """新建节点窗口关闭后，如果保存成功，就刷新列表并选中新节点。"""
        if dialog.saved:
            self.refresh_nodes(select_id=dialog.node_id)

    def delete_selected_node(self):
        """删除当前选中的节点（保留给代码调用，界面入口在右键菜单里）。"""
        node_id = self._selected_node_id()
        if node_id is None:
            messagebox.showinfo(
                '提示', '请先在右边的列表里选中一个节点。', parent=self.root
            )
            return
        self.delete_node(node_id)

    # ------------------------------------------------------------------
    # 复习标记
    # ------------------------------------------------------------------

    def mark_node(self, node_id):
        """
        把某个节点记成「今天忘了」，然后立刻刷新列表。

        同一天重复标记不会报错、也不会多一条记录（数据库用 INSERT OR IGNORE）；
        菜单里已经标过的节点，「忘记了」这一项是灰的，所以这里正常不会重复走到。
        """
        node = db.get_node(node_id)
        if node is None:
            messagebox.showwarning(
                '提示', '这个节点已经不存在了。', parent=self.root
            )
            self.refresh_nodes()
            return

        try:
            db.mark_node(node_id)
        except ValueError as error:
            messagebox.showwarning('提示', str(error), parent=self.root)
            self.refresh_nodes()
            return

        # 立刻按最新数据重画：这一行应该变成红色并跳到最上面
        self.refresh_nodes(select_id=node_id)

        # 日历窗口如果开着，让它上面的红色格子也跟着变
        self._refresh_calendar_if_open()

    def unmark_node(self, node_id):
        """
        撤销「逻辑今天」这个节点的标记（右键菜单的「没忘记」）。

        只删今天这一条记录，以前别的日期留下的标记不受影响；
        删完刷新，红色和置顶都消失，节点回到原来的位置。
        """
        node = db.get_node(node_id)
        if node is None:
            messagebox.showwarning(
                '提示', '这个节点已经不存在了。', parent=self.root
            )
            self.refresh_nodes()
            return

        db.unmark_node(node_id, dates.today_text())

        self.refresh_nodes(select_id=node_id)
        self._refresh_calendar_if_open()

    def _on_marks_changed(self, node_id=None):
        """
        日历窗口里撤销标记后回调这里：主界面列表里的红色要跟着消失。

        node_id 保留参数是为了以后能精确选中，现在一律尽量保持当前选中项。
        """
        self.refresh_nodes(select_id=node_id)

    # ------------------------------------------------------------------
    # 帮助
    # ------------------------------------------------------------------

    def open_help(self):
        """
        打开「使用帮助」小窗（独立窗口，同时只开一个）。

        已经开着就提到前面，不重复创建；帮助内容只读、可以滚动、随时能关。
        """
        window = None
        if self.help_dialog is not None:
            window = self.help_dialog.window
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            return

        self.help_dialog = HelpDialog(self.root)

    # ------------------------------------------------------------------
    # 日历
    # ------------------------------------------------------------------

    def open_calendar(self):
        """
        打开日历窗口（独立窗口，同时只开一个）。

        已经开着就把它提到前面，不重复创建；
        日历里双击节点时，交给主界面的 open_node 打开详情窗。
        """
        window = None
        if self.calendar_dialog is not None:
            window = self.calendar_dialog.window
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            return

        self.calendar_dialog = CalendarDialog(
            self.root,
            on_node_open=self.open_node,
            on_marks_changed=self._on_marks_changed,
        )

    def _refresh_calendar_if_open(self):
        """日历窗口开着的话，让它按最新数据重画（标记变了要及时反映）。"""
        if self.calendar_dialog is None:
            return
        window = self.calendar_dialog.window
        if not window.winfo_exists():
            return
        self.calendar_dialog.reload()
