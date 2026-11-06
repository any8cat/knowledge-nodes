# -*- coding: utf-8 -*-
"""
app/ui_main.py —— 主窗口

职责：
1. 左侧科目区：科目列表 + 右键菜单（空白处新建科目，科目上改名或删除）；
2. 右侧节点区：顶部「日历」「?」按钮 + 搜索框 +「排序」菜单 +
   节点表格（ttk.Treeview）；表格空白处右键新建节点；节点上右键
   「忘记了 / 没忘记 / 打开 / 重命名 / 删除 / 新建节点」；
3. 把用户操作接到 app\\db.py 的增删改查函数上，并在操作后刷新界面。

关于复习标记与统计（任务 03、04）：
- 节点右键选「忘记了」＝记下「逻辑今天忘了它」；选「没忘记」＝撤销今天的标记；
- 节点表格有三列：标题、忘过次数、最近标记日期；链接行显示整组合计，
  统计由 db.list_node_rows 一条 SQL 聚合出来，本文件只负责显示；
- 节点可以按住 Ctrl 多选后链接成一组；链接行用楷体加斜体，成员缩进挂在
  链接行下面，点链接行可以展开/收起；
- 排序由搜索框右侧的「排序：…」菜单选择：
  「按最近浏览时间」「按忘记次数」「按最近忘记时间」，每种都能再选升序或降序；
- 逻辑今天被标记过的节点，无论选哪种排序都**显示红色**；
- 只有「按最近浏览时间 + 降序」这个默认日常模式才**置顶**；其他排序和升序都不置顶，
  否则排序结果就被置顶规则打乱了；
- 红色由数据库算出的 is_marked_today 决定，本文件只照着打 tag，
  不在这里挪行、也不缓存标记状态；
- 标记和撤销都不弹提示、也不写状态栏：列表里变红（或红色消失）本身就是反馈。

说明：
- 节点表格用 ttk.Treeview（不是 Listbox）；有笔记资料的节点，标题后面会显示「[3 附件]」；
- 节点顺序完全由数据库查询决定（三种排序共用 db.list_node_rows 的一条 SQL），
  本文件不做任何排序；
- 「?」按钮打开只读、可滚动的帮助窗（HelpDialog，在 ui_dialogs.py 里）；
- 本文件不写 SQL，也不直接弹节点详情窗、日历窗、帮助窗的界面，
  那些分别在 db.py 与 ui_dialogs.py 里。
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

import db
import dates
from ui_dialogs import CalendarDialog, HelpDialog, NodeDialog, SubjectDialog

# 逻辑今天被标记过的节点：红色加粗（tag 名，与 refresh_nodes 里用的保持一致）
MARKED_TAG = 'marked_today'
MARKED_COLOR = '#C00000'

# 链接行：楷体 + 斜体，和普通节点区分
LINK_TAG = 'link_row'
MARKED_LINK_TAG = 'marked_link_row'

# 搜索命中的行：整行浅黄底色（Treeview 不支持只给单个词上色）
HIGHLIGHT_TAG = 'search_hit'
HIGHLIGHT_COLOR = '#FFF2A8'

# 节点行 iid 前缀 / 链接行 iid 前缀。
# 用前缀区分，避免节点 id 和链接 id 恰好相同、在 Treeview 里撞车。
NODE_IID_PREFIX = 'node:'
LINK_IID_PREFIX = 'link:'


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

        # 记住哪些链接是展开的：刷新列表、搜索、排序后还要保持原来的展开状态。
        # 里面存的是链接 id（整数）。
        self._expanded_link_ids = set()
        # 重建树时 Treeview 会触发 open/close 事件，用这个开关避免把状态写乱。
        self._suspend_tree_events = False
        # 修正「链接行和普通节点一起被多选」时，防止选择事件递归触发。
        self._adjusting_selection = False

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

        # 树形表格：第 0 列显示标题（链接行是父节点，成员缩进挂在下面），
        # 后面两列仍是「忘过次数」「最近标记」。
        # 列宽按窗口 1100 计算：左侧科目区 250 + 边距后，右侧还能剩约 800 像素，
        # 三列合计 740，留出滚动条和边框的余量，内容不会被挤成省略号。
        self.tree = ttk.Treeview(
            tree_frame,
            columns=('mark_count', 'last_mark'),
            show='tree headings',
            selectmode='extended',
        )
        self.tree.heading('#0', text='节点标题')
        self.tree.heading('mark_count', text='忘过次数')
        self.tree.heading('last_mark', text='最近标记')
        self.tree.column('#0', anchor='w', width=500, minwidth=200, stretch=True)
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

        # 链接行：换字体家族（优先楷体）+ 斜体，和普通节点明显区分。
        # 如果系统没有楷体，退回微软雅黑，仍然保留斜体，不会变成方框。
        families = set(tkfont.families(self.root))
        link_family = 'KaiTi' if 'KaiTi' in families else 'Microsoft YaHei'
        self.link_font = tkfont.nametofont('TkDefaultFont').copy()
        self.link_font.configure(family=link_family, slant='italic')
        self.link_bold_font = self.link_font.copy()
        self.link_bold_font.configure(weight='bold')
        self.tree.tag_configure(LINK_TAG, font=self.link_font)
        self.tree.tag_configure(
            MARKED_LINK_TAG, foreground=MARKED_COLOR, font=self.link_bold_font
        )

        # 搜索命中的行整行加浅黄底色。Treeview 不能只给一个词上色，
        # 所以用整行标黄来满足「关键字标黄」的需求。
        self.tree.tag_configure(HIGHLIGHT_TAG, background=HIGHLIGHT_COLOR)

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
        self.tree.bind('<<TreeviewOpen>>', self._on_tree_open)
        self.tree.bind('<<TreeviewClose>>', self._on_tree_close)
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
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

    def refresh_nodes(self, select_id=None, select_link_id=None):
        """
        按「当前科目 + 当前搜索词 + 当前排序方式」重新读取节点并填满右侧表格。

        数据分两次查：
        - db.list_node_rows：链接行 + 没有加入链接的普通节点行，已经在 SQL 里排好序；
        - db.list_link_children：所有链接成员一次查完，界面只负责按 link_id 挂到父行下面。
        这样无论展开多少链接，都不会对每个链接单独查库。

        搜索（在界面层做，因为要给整行标黄）：
        - 普通节点：标题或文字描述包含关键词才显示；
        - 链接：链接名命中，或组内任意成员命中，才显示；
        - 成员命中时自动展开该链接，只显示命中的成员；链接名命中则显示全部成员。

        红色与置顶规则（重要）：
        - 逻辑今天标记过的行，无论选哪种排序都显示红色；
        - 只有「按最近浏览时间 + 降序」的默认日常模式才置顶；
        - 按次数、按最近忘记时间，以及任何升序，都只红不置顶。
        结果为空时用提示文字代替表格。
        """
        keyword = self.keyword_var.get().strip()
        keyword_lower = keyword.lower()
        sort_mode = self.sort_mode_var.get()
        descending = self.sort_order_var.get() == 'desc'

        previous_selection = self.tree.selection()
        self._suspend_tree_events = True
        self.tree.delete(*self.tree.get_children())

        if self.current_subject_id is None:
            self._suspend_tree_events = False
            if not self.subjects:
                self._show_placeholder('请先新建一个科目')
            else:
                self._show_placeholder('请先在左边选中一个科目')
            return

        rows = db.list_node_rows(
            self.current_subject_id,
            sort_mode=sort_mode,
            descending=descending,
        )
        child_rows = db.list_link_children(self.current_subject_id)

        # 按 link_id 分组，成员顺序就是数据库里的 sort_order
        children_by_link = {}
        for child in child_rows:
            children_by_link.setdefault(child['link_id'], []).append(child)

        expanded = set(self._expanded_link_ids)
        inserted = 0

        for row in rows:
            if row['row_type'] == 'link':
                link_id = row['row_id']
                link_name_match = bool(
                    keyword_lower and keyword_lower in row['title'].lower()
                )
                children = children_by_link.get(link_id, [])
                matched_children = [
                    child for child in children
                    if keyword_lower and self._node_matches(child, keyword_lower)
                ]

                # 搜索时：链接名或任一成员命中才保留这一行
                if keyword_lower and not link_name_match and not matched_children:
                    continue

                # 成员命中就自动展开；链接名命中但成员没命中时保持原展开状态
                is_open = link_id in expanded
                if keyword_lower and matched_children and not link_name_match:
                    is_open = True
                if keyword_lower and matched_children:
                    self._expanded_link_ids.add(link_id)

                link_tags = []
                if row['is_marked_today']:
                    link_tags.append(MARKED_LINK_TAG)
                else:
                    link_tags.append(LINK_TAG)
                if link_name_match:
                    link_tags.append(HIGHLIGHT_TAG)

                self.tree.insert(
                    '',
                    'end',
                    iid=LINK_IID_PREFIX + str(link_id),
                    text=row['title'],
                    values=(
                        '%d 次' % row['mark_count'],
                        row['last_mark_date'] or '—',
                    ),
                    tags=tuple(link_tags),
                    open=is_open,
                )
                inserted += 1

                # 链接名命中时显示全部成员；否则只显示命中的成员
                visible_children = children
                if keyword_lower and not link_name_match:
                    visible_children = matched_children
                for child in visible_children:
                    child_match = bool(
                        keyword_lower and self._node_matches(child, keyword_lower)
                    )
                    child_tags = []
                    if child['is_marked_today']:
                        child_tags.append(MARKED_TAG)
                    if child_match:
                        child_tags.append(HIGHLIGHT_TAG)
                    self.tree.insert(
                        LINK_IID_PREFIX + str(link_id),
                        'end',
                        iid=NODE_IID_PREFIX + str(child['node_id']),
                        text=self._node_display_title(child),
                        values=(
                            '%d 次' % child['mark_count'],
                            child['last_mark_date'] or '—',
                        ),
                        tags=tuple(child_tags),
                    )
                    inserted += 1
            else:
                # 普通节点：不在任何链接里，搜索只影响自己这一行
                if keyword_lower and not self._node_matches(row, keyword_lower):
                    continue
                node_tags = []
                if row['is_marked_today']:
                    node_tags.append(MARKED_TAG)
                if keyword_lower:
                    node_tags.append(HIGHLIGHT_TAG)
                self.tree.insert(
                    '',
                    'end',
                    iid=NODE_IID_PREFIX + str(row['row_id']),
                    text=self._node_display_title(row),
                    values=(
                        '%d 次' % row['mark_count'],
                        row['last_mark_date'] or '—',
                    ),
                    tags=tuple(node_tags),
                )
                inserted += 1

        self._suspend_tree_events = False

        if inserted == 0:
            if keyword:
                self._show_placeholder('没有匹配的节点或链接')
            else:
                self._show_placeholder(
                    '这个科目下还没有节点，在下方空白处右键选「新建节点」添加。'
                )
            return

        self._show_tree()

        # 刷新后尽量保持原来的选中行；新建/打开节点时优先选指定的节点
        target_iid = None
        if select_link_id is not None:
            target_iid = LINK_IID_PREFIX + str(select_link_id)
        elif select_id is not None:
            target_iid = NODE_IID_PREFIX + str(select_id)
        elif previous_selection:
            for iid in previous_selection:
                if self.tree.exists(iid):
                    target_iid = iid
                    break

        if target_iid is not None and self.tree.exists(target_iid):
            # 选中的是链接里的节点时，把父链接展开，否则这一行看不见
            parent_iid = self.tree.parent(target_iid)
            if parent_iid:
                self.tree.item(parent_iid, open=True)
                if parent_iid.startswith(LINK_IID_PREFIX):
                    self._expanded_link_ids.add(
                        int(parent_iid[len(LINK_IID_PREFIX):])
                    )
            self.tree.selection_set(target_iid)
            self.tree.focus(target_iid)
            self.tree.see(target_iid)

    def _node_matches(self, node, keyword_lower):
        """节点标题或文字描述里是否包含关键词（不区分英文大小写）。"""
        title = (node['title'] or '').lower()
        content = (node['content'] or '').lower()
        return keyword_lower in title or keyword_lower in content

    def _node_display_title(self, node):
        """节点在列表里的显示文字：标题后面按需加「[N 附件]」。"""
        image_count = node['image_count']
        if image_count:
            return '%s [%d 附件]' % (node['title'], image_count)
        return node['title']

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
        selected_link_id = self._selected_link_id()
        self._update_sort_button_text()
        self.refresh_nodes(
            select_id=selected_id, select_link_id=selected_link_id
        )

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
        """返回右侧表格里当前选中的节点 id；选中的是链接或没选中时返回 None。"""
        selection = self.tree.selection()
        if not selection:
            return None
        iid = selection[0]
        if not iid.startswith(NODE_IID_PREFIX):
            return None
        return int(iid[len(NODE_IID_PREFIX):])

    def _selected_node_ids(self):
        """返回当前选中的所有普通节点 id（按列表里的先后顺序，不含链接行）。"""
        result = []
        for iid in self.tree.selection():
            if iid.startswith(NODE_IID_PREFIX):
                result.append(int(iid[len(NODE_IID_PREFIX):]))
        return result

    def _selected_link_id(self):
        """返回当前选中的链接 id；选中的不是链接时返回 None。"""
        selection = self.tree.selection()
        if not selection:
            return None
        iid = selection[0]
        if not iid.startswith(LINK_IID_PREFIX):
            return None
        return int(iid[len(LINK_IID_PREFIX):])

    def _row_at(self, y):
        """
        按鼠标纵坐标找「真正被点中」的行 iid。

        点在表头、行与行之间的空白，或所有节点下方的空白处时，返回 None，
        这样右键和左键都能区分「点在行上」和「点在空白处」。
        """
        return self.tree.identify_row(y) or None

    def _on_tree_left_click(self, event):
        """
        左键点节点表格：
        - 点链接行（不是左边的小三角）就展开/收起，方便一眼看到组里的节点；
        - 点普通节点行交给 Treeview 正常选中；
        - 点表格下方空白时保持原来的选中项不变，避免误触。
        """
        iid = self._row_at(event.y)
        if iid is None:
            return 'break'

        if iid.startswith(LINK_IID_PREFIX):
            # 点在左侧展开小三角上时交给 Treeview 自己处理，避免展开两次
            element = self.tree.identify_element(event.x, event.y)
            if element == 'Treeitem.indicator':
                return None
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            if self.tree.item(iid, 'open'):
                self.tree.item(iid, open=False)
                self._expanded_link_ids.discard(
                    int(iid[len(LINK_IID_PREFIX):])
                )
            else:
                self.tree.item(iid, open=True)
                self._expanded_link_ids.add(int(iid[len(LINK_IID_PREFIX):]))
            return 'break'
        return None

    def _on_tree_select(self, event=None):
        """
        多选只允许普通知识节点。

        按住 Ctrl 时 Treeview 默认会把链接行也加进选择，这里发现选择里
        既有链接又有普通节点，就把链接行移出选择；如果只选了一个链接，
        则保留它，方便用户看链接的统计。
        """
        if self._suspend_tree_events or self._adjusting_selection:
            return
        selection = list(self.tree.selection())
        links = [iid for iid in selection if iid.startswith(LINK_IID_PREFIX)]
        nodes = [iid for iid in selection if iid.startswith(NODE_IID_PREFIX)]
        if not links:
            return
        if not nodes and len(links) == 1:
            return

        self._adjusting_selection = True
        try:
            for iid in links:
                self.tree.selection_remove(iid)
            if nodes:
                self.tree.focus(nodes[0])
            elif links:
                # 多个链接被同时选中时只保留第一个
                self.tree.selection_set(links[0])
                self.tree.focus(links[0])
        finally:
            self._adjusting_selection = False

    def _on_tree_open(self, event=None):
        """用户展开链接时记住状态，刷新列表后还保持展开。"""
        if self._suspend_tree_events:
            return
        iid = self.tree.focus()
        if iid and iid.startswith(LINK_IID_PREFIX):
            self._expanded_link_ids.add(int(iid[len(LINK_IID_PREFIX):]))

    def _on_tree_close(self, event=None):
        """用户收起链接时记住状态，刷新列表后还保持收起。"""
        if self._suspend_tree_events:
            return
        iid = self.tree.focus()
        if iid and iid.startswith(LINK_IID_PREFIX):
            self._expanded_link_ids.discard(int(iid[len(LINK_IID_PREFIX):]))

    def _on_tree_right_click(self, event):
        """
        右键节点表格。

        - 空白处：只弹「新建节点」；
        - 链接行：只弹「重命名」；
        - 普通节点行：单选时弹节点菜单（含「踢出链接」）；
          多选时弹「全部链接 / 全部删除」。
        """
        iid = self._row_at(event.y)
        if iid is None:
            self.tree.selection_remove(self.tree.selection())
            self._show_node_menu(event, None)
            return 'break'

        # 右键已选中的多选行时保留整组选择，方便直接操作「全部删除」
        if iid in self.tree.selection() and len(self.tree.selection()) > 1:
            pass
        else:
            self.tree.selection_set(iid)
            self.tree.focus(iid)

        if iid.startswith(LINK_IID_PREFIX):
            link_id = int(iid[len(LINK_IID_PREFIX):])
            self._show_link_menu(event, link_id)
            return 'break'

        node_ids = self._selected_node_ids()
        if len(node_ids) >= 2:
            self._show_multi_node_menu(event, node_ids)
        else:
            node_id = int(iid[len(NODE_IID_PREFIX):])
            self._show_node_menu(event, node_id)
        return 'break'

    def _show_link_menu(self, event, link_id):
        """在鼠标位置弹出链接右键菜单：按用户确认，只提供「重命名」。"""
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(
            label='重命名',
            command=lambda lid=link_id: self.root.after_idle(
                lambda: self.rename_link(lid)
            ),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_multi_node_menu(self, event, node_ids):
        """多选普通节点时弹出的菜单：全部链接 / 全部删除。"""
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(
            label='全部链接',
            command=lambda ids=list(node_ids): self.root.after_idle(
                lambda: self.link_selected_nodes(ids)
            ),
        )
        menu.add_command(
            label='全部删除',
            command=lambda ids=list(node_ids): self.root.after_idle(
                lambda: self.delete_selected_nodes(ids)
            ),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

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
            iid = NODE_IID_PREFIX + str(node_id)
            is_marked = MARKED_TAG in self.tree.item(iid, 'tags')

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
            # 只有已经在链接里的节点才显示「踢出链接」
            if db.get_link_of_node(node_id) is not None:
                menu.add_command(
                    label='踢出链接',
                    command=lambda nid=node_id: self.root.after_idle(
                        lambda: self.kick_node(nid)
                    ),
                )
            # 列表写满一页时，表格下方没有空白可点，所以在节点菜单里也放一个
            # 「新建节点」，保证任何时候都能新建，不用先滚到最底下找空白。
            menu.add_separator()
            menu.add_command(
                label='新建节点',
                command=lambda: self.root.after_idle(self.new_node),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_tree_double_click(self, event):
        """双击普通节点打开详情窗；双击链接行展开/收起，不打开节点。"""
        iid = self._row_at(event.y)
        if not iid:
            return
        if iid.startswith(LINK_IID_PREFIX):
            link_id = int(iid[len(LINK_IID_PREFIX):])
            if self.tree.item(iid, 'open'):
                self.tree.item(iid, open=False)
                self._expanded_link_ids.discard(link_id)
            else:
                self.tree.item(iid, open=True)
                self._expanded_link_ids.add(link_id)
            return
        self.tree.selection_set(iid)
        self.open_node(int(iid[len(NODE_IID_PREFIX):]))

    def open_selected_node(self):
        """打开当前选中的节点；选中的是链接时展开该链接。"""
        link_id = self._selected_link_id()
        if link_id is not None:
            self.open_link(link_id)
            return
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

    def link_selected_nodes(self, node_ids):
        """
        把多选中的普通节点链接成一个分组。

        用户点「全部链接」后输入链接名；名字、节点合法性都由 db.create_node_link
        再校验一遍，界面这里只负责给出清楚的错误提示。
        """
        if len(node_ids) < 2:
            messagebox.showinfo(
                '提示', '请按住 Ctrl 至少选中两个节点。', parent=self.root
            )
            return

        name = simpledialog.askstring(
            '全部链接',
            '请输入链接名（同一科目内不能重名，最多 50 个字）：',
            parent=self.root,
        )
        if name is None:
            return

        try:
            link_id = db.create_node_link(
                self.current_subject_id, name, node_ids
            )
        except ValueError as error:
            messagebox.showwarning('提示', str(error), parent=self.root)
            return

        # 新链接默认展开，用户马上能看到组里的节点
        self._expanded_link_ids.add(link_id)
        self.refresh_nodes(select_link_id=link_id)

    def delete_selected_nodes(self, node_ids):
        """多选后的「全部删除」：二次确认后删除节点、附件和标记。"""
        if not node_ids:
            return
        if not messagebox.askyesno(
            '确认删除',
            '确定要删除选中的 %d 个节点吗？\n'
            '它们下面的笔记资料和所有标记也会一起删除，且无法恢复。'
            % len(node_ids),
            parent=self.root,
        ):
            return

        try:
            db.delete_nodes(node_ids)
        except ValueError as error:
            messagebox.showwarning('提示', str(error), parent=self.root)
            return
        self.refresh_nodes()

    def rename_link(self, link_id):
        """给链接改名；链接名规则由 db.rename_node_link 统一校验。"""
        link = db.get_node_link(link_id)
        if link is None:
            messagebox.showwarning(
                '提示', '这个链接已经不存在了。', parent=self.root
            )
            self.refresh_nodes()
            return

        new_name = simpledialog.askstring(
            '重命名链接',
            '请输入新的链接名（同一科目内不能重名，最多 50 个字）：',
            initialvalue=link['name'],
            parent=self.root,
        )
        if new_name is None:
            return
        try:
            db.rename_node_link(link_id, new_name)
        except ValueError as error:
            messagebox.showwarning('提示', str(error), parent=self.root)
            return
        self.refresh_nodes(select_link_id=link_id)

    def kick_node(self, node_id):
        """
        把节点踢出链接，节点本身保留。

        链接里还剩其他成员时链接继续存在；踢掉最后一个成员时链接自动消失。
        不需要二次确认：用户是从该节点的右键菜单明确点的，且节点和资料都不会被删。
        """
        try:
            _link_id, remaining = db.kick_node_from_link(node_id)
        except ValueError as error:
            messagebox.showwarning('提示', str(error), parent=self.root)
            self.refresh_nodes()
            return
        if remaining == 0:
            self._expanded_link_ids.discard(_link_id)
        self.refresh_nodes(select_id=node_id)

    def open_link(self, link_id):
        """从日历双击链接时调用：在主列表里展开并选中这个链接。"""
        if db.get_node_link(link_id) is None:
            self.refresh_nodes()
            return
        self._expanded_link_ids.add(link_id)
        self.refresh_nodes(select_link_id=link_id)

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
            on_link_open=self.open_link,
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
