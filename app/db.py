# -*- coding: utf-8 -*-
"""
app/db.py —— 数据层（SQLite）

职责：
1. 决定数据库放在哪里：永远放在「本文件所在项目根目录」下的 data\\knowledge.db，
   不受启动程序时当前目录的影响；
2. 第一次使用时自动创建 data 目录、自动建 subjects、nodes、node_images、marks
   四张表和必要的索引，已经存在就原样复用，绝不删表重建；
   任务 01、02 建的老数据可以直接升级；
3. 提供科目、节点、笔记图片、复习标记的全部增删改查函数；
4. 提供节点「忘过几次、最近哪天忘的」统计与按次数排序的查询
   （任务 04，全部用一条 SQL 聚合完成）；
5. 负责把图片复制进 data\\attachments\\<节点ID>\\，数据库里只存相对项目根目录的路径。

关于数据目录（任务 04 打包后最容易出错的一条）：
- 普通源码运行：项目根目录 = app 目录的上一级，data 就在 <项目根>\\data；
- 打包成 exe 运行（sys.frozen 为真）：项目根目录 = exe 所在目录，
  data 就在 <exe 所在目录>\\data；
- 无论哪种情况都**不用** PyInstaller 的 _MEIPASS 临时解包目录，
  否则程序一关，写进去的数据就跟着临时目录一起没了。

关于「今天」：本文件里的排序、标记都用 app\\dates.py 的逻辑日，
不自己读系统日期，保证凌晨 0–4 点的行为和界面完全一致。

约定：
- 界面层不许自己写 SQL，一切读写都调用本文件的函数；
- 时间一律存本地时间的 'YYYY-MM-DD HH:MM:SS' 字符串；
- tkinter 是单线程程序，所以整个程序只复用一个数据库连接。
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

import dates

# 项目根目录（也就是「data 文件夹所在的目录」）。
#
# 这里必须分两种情况，是任务 04 打包后最容易出错的地方：
# - 打包成 exe 运行：sys.frozen 为真，基准目录取 exe 自己所在的目录，
#   这样 data 就在 exe 旁边的 data 里，关掉程序数据还在；
# - 普通源码运行：本文件位于 <项目根>\app\db.py，往上两级就是项目根。
#
# 绝对不能用 sys._MEIPASS：那是 PyInstaller 每次启动时解包的临时目录，
# 程序一关就被删掉，写进去的数据会全部丢失。
if getattr(sys, 'frozen', False):
    # 打包后的 exe：sys.executable 就是 D:\...\dist\知识节点\知识节点.exe
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    # 源码运行：app 目录的上一级就是项目根目录
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录与数据库文件（按本文件位置推算，保证 data 永远在项目根目录下）
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'knowledge.db')

# 笔记图片副本的根目录：data\attachments\<节点ID>\
ATTACHMENTS_DIR = os.path.join(DATA_DIR, 'attachments')

# 允许加入的图片扩展名（全部小写，比较前会统一转小写）
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')

# 全项目统一的时间格式：本地时间，精确到秒
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# 全局唯一的数据库连接（第一次用到时才创建）
_connection = None


def now_text():
    """返回当前本地时间的 'YYYY-MM-DD HH:MM:SS' 字符串。"""
    return datetime.now().strftime(TIME_FORMAT)


def get_connection():
    """取得数据库连接；第一次调用时创建 data 目录、连接数据库并建表。"""
    global _connection
    if _connection is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _connection = sqlite3.connect(DB_PATH)
        # 让查询结果可以用 row['字段名'] 的方式取值
        _connection.row_factory = sqlite3.Row
        _create_tables(_connection)
    return _connection


def init_db():
    """程序启动时调用：确保 data 目录和四张表都存在，返回数据库文件的完整路径。"""
    get_connection()
    return DB_PATH


def _create_tables(connection):
    """
    建立四张表和必要的索引；用 IF NOT EXISTS，重复启动不会重建、不会丢数据。

    marks 是任务 03 新增的「复习标记」表：
    - 一条记录 = 某个节点在某一天被标了一次「我忘了」；
    - marked_date 存逻辑日 'YYYY-MM-DD'（凌晨 4 点为界，见 app\\dates.py）；
    - (node_id, marked_date) 建唯一索引，从数据库层面保证
      「同一节点同一天只有一条记录」，不依赖界面按钮去拦。
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_viewed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_nodes_subject_id ON nodes (subject_id);

        CREATE TABLE IF NOT EXISTS node_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_node_images_node_id ON node_images (node_id);

        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL,
            marked_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_marks_node_id_marked_date
            ON marks (node_id, marked_date);
        """
    )
    connection.commit()


# ---------------------------------------------------------------------------
# 科目相关的增删改查
# ---------------------------------------------------------------------------

def create_subject(name):
    """新建一个科目，返回新科目的 id。"""
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'INSERT INTO subjects (name, created_at) VALUES (?, ?)',
            (name, now_text()),
        )
    return cursor.lastrowid


def get_subject(subject_id):
    """按 id 查一个科目，找不到返回 None。"""
    row = get_connection().execute(
        'SELECT id, name, created_at FROM subjects WHERE id = ?',
        (subject_id,),
    ).fetchone()
    return row


def list_subjects():
    """查出全部科目，按建立先后排序。"""
    rows = get_connection().execute(
        'SELECT id, name, created_at FROM subjects ORDER BY id ASC'
    ).fetchall()
    return list(rows)


def rename_subject(subject_id, new_name):
    """给科目改名；成功返回 True，科目不存在返回 False。"""
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'UPDATE subjects SET name = ? WHERE id = ?',
            (new_name, subject_id),
        )
    return cursor.rowcount > 0


def delete_subject(subject_id):
    """
    删除一个科目，并连带删除它下面的所有节点、图片记录、标记记录和附件文件夹。

    图片记录、标记记录、附件文件夹、节点、科目全部放在同一个事务里，
    任何一步失败都会整体回滚，不会留下半截数据。
    """
    connection = get_connection()

    # 先查出这个科目下的所有节点 id，后面要按节点清理附件
    node_rows = connection.execute(
        'SELECT id FROM nodes WHERE subject_id = ?',
        (subject_id,),
    ).fetchall()
    node_ids = [row['id'] for row in node_rows]

    with connection:
        # 先删这些节点的图片记录和标记记录
        if node_ids:
            placeholders = ', '.join('?' for _ in node_ids)
            connection.execute(
                'DELETE FROM node_images WHERE node_id IN (%s)' % placeholders,
                node_ids,
            )
            connection.execute(
                'DELETE FROM marks WHERE node_id IN (%s)' % placeholders,
                node_ids,
            )

        # 再逐个删除节点对应的附件文件夹
        for node_id in node_ids:
            shutil.rmtree(attachments_dir(node_id), ignore_errors=True)

        # 最后删节点和科目本身
        connection.execute(
            'DELETE FROM nodes WHERE subject_id = ?',
            (subject_id,),
        )
        cursor = connection.execute(
            'DELETE FROM subjects WHERE id = ?',
            (subject_id,),
        )
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# 节点相关的增删改查
# ---------------------------------------------------------------------------

def _like_pattern(keyword):
    """把关键词转成 LIKE 用的模糊匹配串，并把 %、_、\\ 三个特殊字符转义掉。"""
    text = keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return '%' + text + '%'


def _fetch_nodes(subject_id, keyword=None, sort_by_marks=False):
    """
    内部函数：按科目取节点，一次查完每个节点的「标记总次数」和「最近一次标记日期」。

    两种排序共用这一个查询，只有最后一段 ORDER BY 不同，避免写两份重复代码：
    - 日常模式（sort_by_marks=False）：逻辑今天被标记过的节点置顶并显示红色；
      其余按最近打开时间倒序，从没打开过的按创建时间倒序。
    - 临考模式（sort_by_marks=True）：按标记总次数从多到少；次数相同按最近标记
      日期从新到旧；从未标记过的排最后。此模式下当天标记的节点**仍然显示红色**
      （is_marked_today 照常返回），但 ORDER BY 里故意不含 is_marked_today，
      所以**不再置顶**——否则「按次数排序」就被置顶规则打乱了。

    次数统计用 LEFT JOIN 一个聚合子查询（COUNT / MAX）一次算完，
    不在 Python 里对每个节点各查一次数据库，节点上百条时也不会卡。
    这里必须用 LEFT JOIN：用 INNER JOIN 会让从没标记过的节点整行消失，
    列表里就只剩「忘过」的节点了。

    除统计外还带出两个字段供界面使用：
    - image_count：这个节点有几张笔记图片，主界面用它显示「[3 图]」；
    - is_marked_today：1 表示逻辑今天被标记过，界面据此把整行显示成红色。

    「今天有没有被标记」用 LEFT JOIN + 唯一索引判断：
    (node_id, marked_date) 唯一，所以一个节点最多关联出一行，不会把节点查重。
    """
    today = dates.today_text()
    sql = (
        'SELECT n.id, n.subject_id, n.title, n.content, n.created_at, n.last_viewed_at, '
        '(SELECT COUNT(*) FROM node_images i WHERE i.node_id = n.id) AS image_count, '
        'CASE WHEN m.id IS NULL THEN 0 ELSE 1 END AS is_marked_today, '
        'COALESCE(agg.mark_count, 0) AS mark_count, '
        'agg.last_mark_date AS last_mark_date '
        'FROM nodes n '
        'LEFT JOIN marks m ON m.node_id = n.id AND m.marked_date = ? '
        'LEFT JOIN ('
        '    SELECT node_id, COUNT(*) AS mark_count, MAX(marked_date) AS last_mark_date '
        '    FROM marks GROUP BY node_id'
        ') agg ON agg.node_id = n.id '
        'WHERE n.subject_id = ?'
    )
    params = [today, subject_id]
    if keyword:
        pattern = _like_pattern(keyword)
        sql += " AND (n.title LIKE ? ESCAPE '\\' OR n.content LIKE ? ESCAPE '\\')"
        params.append(pattern)
        params.append(pattern)

    if sort_by_marks:
        # 临考模式：次数降序 → 最近标记日期降序（NULL 在 SQLite 里最小，
        # DESC 时自然排最后）→ 再按最近打开、创建时间兜底，保证顺序稳定。
        # 注意：这里没有 is_marked_today，所以当天标记的节点只显示红色、不置顶。
        sql += (
            ' ORDER BY COALESCE(agg.mark_count, 0) DESC, '
            '(agg.last_mark_date IS NULL) ASC, agg.last_mark_date DESC, '
            '(n.last_viewed_at IS NULL) ASC, n.last_viewed_at DESC, '
            'n.created_at DESC, n.id DESC'
        )
    else:
        # 日常模式：当天标记的置顶（红色同时保留），再按最近打开时间排序。
        sql += (
            ' ORDER BY is_marked_today DESC, (n.last_viewed_at IS NULL) ASC, '
            'n.last_viewed_at DESC, n.created_at DESC, n.id DESC'
        )

    rows = get_connection().execute(sql, params).fetchall()
    return list(rows)


def create_node(subject_id, title, content=''):
    """在指定科目下新建一个节点，返回新节点的 id。"""
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'INSERT INTO nodes (subject_id, title, content, created_at, last_viewed_at) '
            'VALUES (?, ?, ?, ?, NULL)',
            (subject_id, title, content, now_text()),
        )
    return cursor.lastrowid


def get_node(node_id):
    """
    按 id 查一个节点，找不到返回 None。

    返回值里也带 image_count，界面可以知道这个节点有几张图。
    """
    row = get_connection().execute(
        'SELECT n.id, n.subject_id, n.title, n.content, n.created_at, n.last_viewed_at, '
        '(SELECT COUNT(*) FROM node_images i WHERE i.node_id = n.id) AS image_count '
        'FROM nodes n WHERE n.id = ?',
        (node_id,),
    ).fetchone()
    return row


def list_nodes(subject_id, keyword=None, sort_by_marks=False):
    """
    查某个科目下的节点，可选搜索关键词，可选两种排序。

    sort_by_marks=False：日常排序（今天标记的置顶并显示红色，其余按最近打开时间）；
    sort_by_marks=True：临考排序（按忘过次数从多到少，当天标记仍红但不置顶）。

    搜索与排序都在这一个函数里完成，主界面两种模式都调用它。
    """
    if keyword is None:
        keyword = ''
    keyword = keyword.strip()
    return _fetch_nodes(subject_id, keyword if keyword else None, sort_by_marks)


def search_nodes(subject_id, keyword):
    """按关键词搜节点（日常排序）；保留这个函数名，兼容原来的调用。"""
    return list_nodes(subject_id, keyword, False)


def list_nodes_by_marks(subject_id, keyword=None):
    """按「忘过次数」排序查节点，可带搜索关键词（内部与日常排序共用一条 SQL）。"""
    return list_nodes(subject_id, keyword, True)


def update_node(node_id, title, content):
    """修改节点的标题与文字描述；成功返回 True，节点不存在返回 False。"""
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'UPDATE nodes SET title = ?, content = ? WHERE id = ?',
            (title, content, node_id),
        )
    return cursor.rowcount > 0


def delete_node(node_id):
    """
    删除一个节点，并连带删除它下面的所有图片记录、标记记录和附件文件夹。

    顺序：先删 node_images 与 marks 记录，再删 data\\attachments\\<节点ID>\\ 文件夹，
    最后删 nodes 行；整个过程在同一个事务里。
    成功返回 True，节点不存在返回 False。
    """
    connection = get_connection()
    folder = attachments_dir(node_id)

    with connection:
        connection.execute(
            'DELETE FROM node_images WHERE node_id = ?',
            (node_id,),
        )
        # 标记记录跟着节点一起删，避免留下指向不存在节点的孤儿数据
        connection.execute(
            'DELETE FROM marks WHERE node_id = ?',
            (node_id,),
        )
        # 文件夹不存在时 rmtree 也不会报错，统一用 ignore_errors
        shutil.rmtree(folder, ignore_errors=True)
        cursor = connection.execute(
            'DELETE FROM nodes WHERE id = ?',
            (node_id,),
        )
    return cursor.rowcount > 0


def touch_node_viewed(node_id):
    """把节点的 last_viewed_at 更新为当前时间（打开节点详情时调用）。"""
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'UPDATE nodes SET last_viewed_at = ? WHERE id = ?',
            (now_text(), node_id),
        )
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# 笔记图片相关的增删改查
# ---------------------------------------------------------------------------

def attachments_dir(node_id):
    """返回某个节点存放图片副本的文件夹完整路径。"""
    return os.path.join(ATTACHMENTS_DIR, str(node_id))


def image_absolute_path(stored_path):
    """
    把数据库里的相对路径（例如 data\\attachments\\12\\笔记.jpg）
    转成当前电脑上可以直接打开的真实路径。

    如果旧数据里意外存的是绝对路径，就原样返回，保证文件还能打开。
    """
    if os.path.isabs(stored_path):
        return stored_path
    return os.path.join(BASE_DIR, stored_path)


def _unique_file_path(folder, filename):
    """
    在 folder 里挑一个不会覆盖已有文件的名字。

    重名时依次尝试：原名 → 名字_1.扩展名 → 名字_2.扩展名 …
    返回完整的绝对路径。
    """
    name, extension = os.path.splitext(filename)
    candidate = filename
    number = 1

    while os.path.exists(os.path.join(folder, candidate)):
        candidate = '%s_%d%s' % (name, number, extension)
        number += 1

    return os.path.join(folder, candidate)


def _remove_file_quietly(path):
    """删除一个文件，不存在或删不掉都不向外抛异常（用于失败回滚）。"""
    try:
        os.remove(path)
    except OSError:
        pass


def store_image_file(node_id, source_path):
    """
    把一张图片复制进 data\\attachments\\<节点ID>\\ 并写入数据库记录。

    规则：
    1. 保留原文件名；
    2. 重名时自动加 _1、_2 后缀，绝不覆盖已有文件；
    3. 数据库里存相对项目根目录的路径，整个项目文件夹拷走还能用；
    4. 新图片排在最后；
    5. 任何一步失败都把已经复制的文件删掉，不留下垃圾。

    返回新图片记录的 id。
    """
    if get_node(node_id) is None:
        raise ValueError('节点已经不存在，无法添加图片。')

    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise FileNotFoundError('找不到图片文件：%s' % source_path)

    extension = os.path.splitext(source_path)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValueError('不支持的图片类型：%s' % extension)

    folder = attachments_dir(node_id)
    os.makedirs(folder, exist_ok=True)

    # 先挑一个不冲突的目标文件名，再复制
    target_path = _unique_file_path(folder, os.path.basename(source_path))

    try:
        shutil.copy2(source_path, target_path)
    except Exception:
        _remove_file_quietly(target_path)
        raise

    # 复制完再确认一次文件真的在，避免磁盘异常时留下空记录
    if not os.path.exists(target_path):
        raise OSError('图片复制失败，目标文件不存在：%s' % target_path)

    # 存相对项目根目录的路径，例如 data\attachments\12\笔记第1页.jpg
    stored_path = os.path.relpath(target_path, BASE_DIR)

    try:
        return add_node_image(
            node_id,
            os.path.basename(target_path),
            stored_path,
            next_image_sort_order(node_id),
        )
    except Exception:
        # 数据库写入失败，把刚复制的文件删掉，保持数据库和磁盘一致
        _remove_file_quietly(target_path)
        raise


def list_node_images(node_id):
    """按顺序列出某个节点的全部图片（sort_order 小的在前）。"""
    rows = get_connection().execute(
        'SELECT id, node_id, filename, stored_path, sort_order, created_at '
        'FROM node_images WHERE node_id = ? '
        'ORDER BY sort_order ASC, id ASC',
        (node_id,),
    ).fetchall()
    return list(rows)


def get_node_image(image_id):
    """按 id 取一张图片的记录，找不到返回 None。"""
    row = get_connection().execute(
        'SELECT id, node_id, filename, stored_path, sort_order, created_at '
        'FROM node_images WHERE id = ?',
        (image_id,),
    ).fetchone()
    return row


def count_node_images(node_id):
    """统计某个节点下有几张图片。"""
    row = get_connection().execute(
        'SELECT COUNT(*) AS count FROM node_images WHERE node_id = ?',
        (node_id,),
    ).fetchone()
    return row['count']


def next_image_sort_order(node_id):
    """返回某个节点下一张图片应该用的排序号（当前最大号加 1）。"""
    row = get_connection().execute(
        'SELECT MAX(sort_order) AS max_order FROM node_images WHERE node_id = ?',
        (node_id,),
    ).fetchone()

    if row is None or row['max_order'] is None:
        return 1
    return row['max_order'] + 1


def add_node_image(node_id, filename, stored_path, sort_order):
    """新增一条图片记录，返回新记录的 id。"""
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'INSERT INTO node_images '
            '(node_id, filename, stored_path, sort_order, created_at) '
            'VALUES (?, ?, ?, ?, ?)',
            (node_id, filename, stored_path, sort_order, now_text()),
        )
    return cursor.lastrowid


def delete_node_image(image_id):
    """
    删除一条图片记录，返回被删记录里的 stored_path。

    注意：这里只删数据库记录，磁盘上的那份文件由界面层负责删，
    因为界面层需要先知道路径，才能决定删文件失败时怎么提示。
    记录不存在时返回 None。
    """
    connection = get_connection()
    row = connection.execute(
        'SELECT stored_path FROM node_images WHERE id = ?',
        (image_id,),
    ).fetchone()

    if row is None:
        return None

    with connection:
        connection.execute(
            'DELETE FROM node_images WHERE id = ?',
            (image_id,),
        )

    return row['stored_path']


def swap_node_image_order(image_id_a, image_id_b):
    """
    交换两张图片的 sort_order，用来实现上移、下移。

    两条记录必须都存在，否则返回 False。
    """
    connection = get_connection()
    rows = connection.execute(
        'SELECT id, sort_order FROM node_images WHERE id IN (?, ?)',
        (image_id_a, image_id_b),
    ).fetchall()

    if len(rows) != 2:
        return False

    order = {row['id']: row['sort_order'] for row in rows}

    # 两条记录排序号相同就没必要交换（正常情况下不会出现）
    if order[image_id_a] == order[image_id_b]:
        return False

    with connection:
        connection.execute(
            'UPDATE node_images SET sort_order = ? WHERE id = ?',
            (order[image_id_b], image_id_a),
        )
        connection.execute(
            'UPDATE node_images SET sort_order = ? WHERE id = ?',
            (order[image_id_a], image_id_b),
        )

    return True


def reorder_node_images(node_id, ordered_image_ids):
    """
    按界面拖动后的顺序，重写一个节点下所有图片的 sort_order。

    ordered_image_ids 必须是这个节点当前全部图片 id 的一个排列，
    少一个、多一个、重复或混入别的节点的 id 都会报错，
    避免拖动过程中出问题把顺序写乱。

    顺序号从 1 开始连续编号；成功返回 True。
    """
    connection = get_connection()
    rows = connection.execute(
        'SELECT id FROM node_images WHERE node_id = ?',
        (node_id,),
    ).fetchall()
    existing_ids = [row['id'] for row in rows]

    try:
        new_ids = [int(image_id) for image_id in ordered_image_ids]
    except (TypeError, ValueError):
        raise ValueError('拖动后的图片顺序不正确，请重新拖动。')

    if (
        len(new_ids) != len(existing_ids)
        or len(set(new_ids)) != len(new_ids)
        or set(new_ids) != set(existing_ids)
    ):
        raise ValueError('图片顺序和数据库不一致，请关闭详情窗后重新打开再试。')

    with connection:
        for index, image_id in enumerate(new_ids, start=1):
            connection.execute(
                'UPDATE node_images SET sort_order = ? WHERE id = ? AND node_id = ?',
                (index, image_id, node_id),
            )
    return True


def _normalize_image_filename(current_filename, requested_name):
    """
    校验并整理「重命名图片」时输入的新文件名。

    规则：
    - 不能为空，不能带路径，不能含 Windows 文件名禁用字符；
    - 不写扩展名时自动沿用原扩展名；
    - 扩展名必须和原来一致，避免把 png 内容改成 .jpg 后缀；
    - 不接受 CON、PRN 这类 Windows 保留名；
    - 和原名完全相同就原样返回，由调用方当作没改。
    """
    requested_name = requested_name.strip()
    if not requested_name:
        raise ValueError('文件名不能为空。')

    if os.path.basename(requested_name) != requested_name:
        raise ValueError('文件名里不能带文件夹路径。')

    if requested_name in ('.', '..'):
        raise ValueError('这个文件名不能用。')

    if any(ord(char) < 32 for char in requested_name):
        raise ValueError('文件名里不能有控制字符。')

    if any(char in '<>:"/\\|?*' for char in requested_name):
        raise ValueError('文件名里不能包含 < > : " / \\ | ? * 这些字符。')

    if requested_name.endswith('.'):
        raise ValueError('文件名不能以句点结尾。')

    old_extension = os.path.splitext(current_filename)[1]
    name, extension = os.path.splitext(requested_name)

    if not extension:
        # 用户只写了名字，自动补回原来的扩展名
        requested_name = requested_name + old_extension
        name, extension = os.path.splitext(requested_name)

    if not name:
        raise ValueError('文件名不能只有扩展名。')

    if old_extension and extension.lower() != old_extension.lower():
        raise ValueError(
            '扩展名要和原来一致（%s），不能改成 %s。'
            % (old_extension, extension)
        )

    if len(requested_name) > 200:
        raise ValueError('文件名太长了，请控制在 200 个字符以内。')

    # Windows 不允许把 CON、PRN、AUX、NUL、COM1~9、LPT1~9 当作文件名
    reserved = {'CON', 'PRN', 'AUX', 'NUL'}
    reserved.update('COM%d' % number for number in range(1, 10))
    reserved.update('LPT%d' % number for number in range(1, 10))
    if requested_name.split('.')[0].upper() in reserved:
        raise ValueError('这个文件名是 Windows 保留名，请换一个。')

    return requested_name


def rename_node_image_file(image_id, requested_name):
    """
    给一张图片重命名：磁盘上的副本和数据库里的 filename、stored_path 一起改。

    只改文件名，不换文件夹，也不动 sort_order。
    成功返回新文件名；失败抛异常，由界面层显示具体原因：
    - ValueError：名字不合法、扩展名不一致、记录不存在；
    - FileNotFoundError：磁盘上的文件已经丢了；
    - FileExistsError：同文件夹里已经有同名文件（绝不覆盖）。

    做法是「先更新数据库，再改磁盘文件名」；改磁盘失败时把数据库改回原样，
    保证不会出现数据库指向一个不存在的新名字。
    """
    image = get_node_image(image_id)
    if image is None:
        raise ValueError('这条图片记录已经不存在了。')

    old_filename = image['filename']
    new_filename = _normalize_image_filename(old_filename, requested_name)

    if new_filename == old_filename:
        # 名字没变，直接当作成功，不碰磁盘
        return old_filename

    if new_filename.lower() == old_filename.lower():
        raise ValueError('新文件名和原名只有大小写不同，请换一个名字。')

    old_path = image_absolute_path(image['stored_path'])
    if not os.path.isfile(old_path):
        raise FileNotFoundError('磁盘上的图片文件已经丢失：%s' % old_path)

    folder = os.path.dirname(old_path)
    new_path = os.path.join(folder, new_filename)
    if os.path.exists(new_path):
        raise FileExistsError('同名文件已存在：%s' % new_filename)

    new_stored_path = os.path.relpath(new_path, BASE_DIR)
    connection = get_connection()

    with connection:
        cursor = connection.execute(
            'UPDATE node_images SET filename = ?, stored_path = ? WHERE id = ?',
            (new_filename, new_stored_path, image_id),
        )
    if cursor.rowcount == 0:
        raise ValueError('这条图片记录已经不存在了。')

    try:
        os.rename(old_path, new_path)
    except OSError:
        # 磁盘改名失败，把数据库改回原样，避免记录指向不存在的新文件
        with connection:
            connection.execute(
                'UPDATE node_images SET filename = ?, stored_path = ? WHERE id = ?',
                (old_filename, image['stored_path'], image_id),
            )
        raise

    return new_filename


def delete_node_images(node_id):
    """
    删除某个节点下的全部图片记录，返回删除的条数。

    只删数据库记录，不删磁盘文件；删节点、删科目时由调用方清理文件夹。
    """
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'DELETE FROM node_images WHERE node_id = ?',
            (node_id,),
        )
    return cursor.rowcount


# ---------------------------------------------------------------------------
# 复习标记（marks）相关的增删改查
# ---------------------------------------------------------------------------

def mark_node(node_id, marked_date=None):
    """
    把某个节点标记为「我忘了」。

    - marked_date 不给时，用 app\\dates.py 的逻辑今天（'YYYY-MM-DD'）；
    - 同一天重复标记不报错、也不新增记录（靠 (node_id, marked_date) 唯一索引）；
    - 返回 True 表示这次真的新增了一条，False 表示这一天本来就已经标过。

    节点不存在时抛 ValueError，由界面层提示用户。
    """
    if marked_date is None:
        marked_date = dates.today_text()
    if get_node(node_id) is None:
        raise ValueError('节点已经不存在，无法标记。')

    connection = get_connection()
    with connection:
        # INSERT OR IGNORE：撞上唯一索引就静默跳过，不抛异常、不多写一行
        cursor = connection.execute(
            'INSERT OR IGNORE INTO marks (node_id, marked_date, created_at) '
            'VALUES (?, ?, ?)',
            (node_id, marked_date, now_text()),
        )
    return cursor.rowcount > 0


def unmark_node(node_id, marked_date):
    """
    撤销「某个节点在某一天」的标记。

    返回 True 表示删掉了一条记录，False 表示这一天本来就没有标记。
    """
    connection = get_connection()
    with connection:
        cursor = connection.execute(
            'DELETE FROM marks WHERE node_id = ? AND marked_date = ?',
            (node_id, marked_date),
        )
    return cursor.rowcount > 0


def list_marks_of_date(subject_id, marked_date):
    """
    查某一天、某个科目下被标记了哪些节点。

    返回的行里带 mark_id（撤销时用）、node_id（双击打开详情用）、
    node_title、subject_name（日历下方显示「科目名 › 节点标题」）。
    按标记时间从早到晚排，同一秒时用 id 兜底，顺序稳定。
    """
    rows = get_connection().execute(
        'SELECT m.id AS mark_id, m.node_id, m.marked_date, m.created_at, '
        'n.title AS node_title, s.name AS subject_name '
        'FROM marks m '
        'JOIN nodes n ON n.id = m.node_id '
        'JOIN subjects s ON s.id = n.subject_id '
        'WHERE n.subject_id = ? AND m.marked_date = ? '
        'ORDER BY m.created_at ASC, m.id ASC',
        (subject_id, marked_date),
    ).fetchall()
    return list(rows)


def count_marks_by_day(subject_id, year, month):
    """
    查某个月、某个科目里「每天各标了几个节点」。

    参数：subject_id 科目 id，year 年（例如 2026），month 月（1–12）。
    返回字典：{'2026-10-28': 2, '2026-10-29': 1, …}；
    没有标记的日期不会出现在字典里，调用方用 get(日期, 0) 取。

    注意：上限必须按「当前科目 + 当前月份」统计，不能把别的科目算进来，
    否则日历的红色深浅会不对。
    """
    month_prefix = '%04d-%02d' % (year, month)
    rows = get_connection().execute(
        'SELECT m.marked_date AS marked_date, COUNT(*) AS mark_count '
        'FROM marks m '
        'JOIN nodes n ON n.id = m.node_id '
        'WHERE n.subject_id = ? AND substr(m.marked_date, 1, 7) = ? '
        'GROUP BY m.marked_date',
        (subject_id, month_prefix),
    ).fetchall()
    return {row['marked_date']: row['mark_count'] for row in rows}


def count_node_marks(node_id):
    """
    查某个节点一共被标记过多少次（同一天只算一次）。

    本任务先把这个函数写出来，留给任务 04 的「按忘过次数排序」用。
    """
    row = get_connection().execute(
        'SELECT COUNT(*) AS mark_count FROM marks WHERE node_id = ?',
        (node_id,),
    ).fetchone()
    if row is None:
        return 0
    return row['mark_count']


def last_mark_date(node_id):
    """
    查某个节点最近一次被标记的日期（'YYYY-MM-DD'）。

    从来没被标记过时返回 None。本任务先写出来，留给任务 04 用。
    """
    row = get_connection().execute(
        'SELECT MAX(marked_date) AS last_date FROM marks WHERE node_id = ?',
        (node_id,),
    ).fetchone()
    if row is None or row['last_date'] is None:
        return None
    return row['last_date']


def default_calendar_subject_id():
    """
    算日历窗口默认该显示哪个科目，返回科目 id；一个科目都没有时返回 None。

    规则（顺序不能反）：
    1. 先找「最近打开过节点的那一科」——取所有节点里 last_viewed_at 最大的那条，
       用它的 subject_id；
    2. 如果一个节点都没打开过（last_viewed_at 全为空），
       就取创建时间最早的那一科（created_at 最小）；
    3. 一个科目都没有 → 返回 None。
    """
    connection = get_connection()

    row = connection.execute(
        'SELECT subject_id FROM nodes '
        'WHERE last_viewed_at IS NOT NULL AND last_viewed_at <> \'\' '
        'ORDER BY last_viewed_at DESC, id DESC LIMIT 1'
    ).fetchone()
    if row is not None:
        return row['subject_id']

    row = connection.execute(
        'SELECT id FROM subjects ORDER BY created_at ASC, id ASC LIMIT 1'
    ).fetchone()
    if row is not None:
        return row['id']
    return None
