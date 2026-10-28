# -*- coding: utf-8 -*-
"""
app/main.py —— 程序入口

职责：
1. 启动时确保数据库与 data 目录已经就绪；
2. 创建主窗口（标题「知识节点」、初始大小 1100x700）；
3. 把主窗口交给 app\\ui_main.py 里的界面类，然后进入事件循环。

说明：本文件只做「启动」这一件事，不写任何业务逻辑。
"""

from tkinterdnd2 import TkinterDnD

import db
from ui_main import MainWindow


def main():
    """创建主窗口并启动程序。"""
    # 先准备好数据库（第一次运行会自动建 data 目录和三张表）
    db.init_db()

    # 必须用 TkinterDnD.Tk（而不是 tk.Tk）：它会加载拖放组件，
    # 否则节点详情窗收不到「从资源管理器拖进来的文件」。
    root = TkinterDnD.Tk()
    root.title('知识节点')
    root.geometry('1100x700')
    root.minsize(900, 560)

    MainWindow(root)
    root.mainloop()


if __name__ == '__main__':
    main()
