#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import bisect
import threading
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ================== 业务逻辑函数 ==================

def read_text_lines(path):
    """
    以多编码回退方式读取文本行，最大程度兼容 GBK/UTF-8/ANSI 等。
    """
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'cp936', 'latin-1']
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.readlines()
        except Exception:
            continue
    # 最后兜底：忽略解码错误
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.readlines()


def read_t1_secs_from_lines(lines):
    """
    从 T1 文件行中解析秒数列表（允许首行或某行是 'Secs' 表头）。
    支持每行一个数，或空白分隔多个数；非数字 token 自动忽略。
    """
    secs = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower == 'secs' or lower.startswith('secs'):
            tokens = line.split()
            if len(tokens) == 1:
                # 仅 'Secs' 一词，整行跳过
                continue
            candidates = tokens[1:]
        else:
            candidates = line.split()

        for tok in candidates:
            try:
                secs.append(float(tok))
            except ValueError:
                pass
    return secs


def read_t3_temp_from_lines(lines):
    """
    从TG时间(s)行中解析：
    - 定位包含 'Time' 且包含 'Temperature' 的表头行
    - 表头之后每行前两列分别为 Time(min) 与 Temperature
    返回：times(list[float]), temps(list[float])
    """
    times, temps = [], []
    data_started = False

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if not data_started:
            l = line.lower()
            if ('time' in l) and ('temperature' in l):
                data_started = True
            continue

        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0])
            temp = float(parts[1])
        except ValueError:
            continue

        times.append(t)
        temps.append(temp)

    # 确保按时间升序
    if times and any(times[i] > times[i+1] for i in range(len(times)-1)):
        paired = sorted(zip(times, temps), key=lambda x: x[0])
        times, temps = [list(x) for x in zip(*paired)]

    return times, temps


def closest_index(sorted_list, x):
    """
    在已排序列表中寻找与 x 最近的索引；若左右等距，取左侧（更早时间）。
    """
    if not sorted_list:
        return None
    i = bisect.bisect_left(sorted_list, x)
    n = len(sorted_list)
    if i == 0:
        return 0
    if i == n:
        return n - 1
    before = sorted_list[i-1]
    after = sorted_list[i]
    if abs(after - x) < abs(x - before):
        return i
    else:
        return i - 1


def adjust_consecutive_duplicates(values, step=0.015, rounding=3):
    """
    对连续相同的温度做微调：
    - 同一“相同段”中，从第二个开始依次 + step
      （第二个 +1*step，第三个 +2*step，…）
    - 其他不变
    """
    if not values:
        return []

    adjusted = values[:]
    i, n = 0, len(adjusted)
    while i < n:
        j = i + 1
        while j < n and adjusted[j] == adjusted[i]:
            j += 1
        # 段 [i, j) 长度>=2 才处理
        for k in range(i + 1, j):
            delta = (k - i) * step
            adjusted[k] = round(adjusted[i] + delta, rounding)
        i = j
    return adjusted


def process_match(t1_path, stad_path, out_path, step=0.015, rounding=3):
    """
    读取、匹配、微调并导出 CSV。
    返回 (header, rows) 以便界面预览。
    """
    # 1) 读 T1（秒）并转分钟
    t1_lines = read_text_lines(t1_path)
    t1_secs = read_t1_secs_from_lines(t1_lines)
    if not t1_secs:
        raise ValueError("未在 T1 文件中解析出任何秒数。")

    t2_mins = [s / 60.0 for s in t1_secs]

    # 2) 读 T3 与 Temperature
    stad_lines = read_text_lines(stad_path)
    t3_times, temps = read_t3_temp_from_lines(stad_lines)
    if not t3_times:
        raise ValueError("未在TG时间(s)中找到有效的 Time/Temperature 数据。")

    # 3) 匹配最近 T3
    matched_t3, matched_temp = [], []
    for t2 in t2_mins:
        idx = closest_index(t3_times, t2)
        if idx is None:
            raise ValueError("Time 列为空，无法匹配。")
        matched_t3.append(t3_times[idx])
        matched_temp.append(temps[idx])

    # 4) 连续相同值微调
    final_temp = adjust_consecutive_duplicates(
        matched_temp, step=float(step), rounding=int(rounding)
    )

    # 5) 写出 CSV
    header = ['T1_Secs', 'T2_Min', 'Matched_T3_Min', 'Raw_Temperature', 'Final_Temperature']
    rows = [
        [
            round(t1_secs[i], 3),
            round(t2_mins[i], 6),
            round(matched_t3[i], 6),
            round(matched_temp[i], rounding),
            round(final_temp[i], rounding),
        ]
        for i in range(len(t1_secs))
    ]

    # 自动补 .csv
    if out_path and not out_path.lower().endswith('.csv'):
        out_path = out_path + '.csv'

    if out_path:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    return header, rows, out_path

# ================== Tkinter GUI ==================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("时间-温度映射")
        self.geometry("900x600")

        self.t1_path = tk.StringVar()
        self.stad_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.step = tk.StringVar(value="0.015")
        self.rounding = tk.IntVar(value=3)

        self._build_ui()

    def _build_ui(self):
        pad = {'padx': 8, 'pady': 6}

        frm = ttk.Frame(self)
        frm.pack(fill='x', **pad)

        # T1 文件
        ttk.Label(frm, text="IR时间(s)：").grid(row=0, column=0, sticky='e')
        ttk.Entry(frm, textvariable=self.t1_path, width=70).grid(row=0, column=1, sticky='we')
        ttk.Button(frm, text="选择…", command=self.choose_t1).grid(row=0, column=2, sticky='w', padx=4)

        # STAD 文件
        ttk.Label(frm, text="TG时间(s)：").grid(row=1, column=0, sticky='e')
        ttk.Entry(frm, textvariable=self.stad_path, width=70).grid(row=1, column=1, sticky='we')
        ttk.Button(frm, text="选择…", command=self.choose_stad).grid(row=1, column=2, sticky='w', padx=4)

        # 输出路径
        ttk.Label(frm, text="输出 CSV：").grid(row=2, column=0, sticky='e')
        ttk.Entry(frm, textvariable=self.out_path, width=70).grid(row=2, column=1, sticky='we')
        ttk.Button(frm, text="保存到…", command=self.choose_out).grid(row=2, column=2, sticky='w', padx=4)

        # 参数
        # 参数（行3）：左边是标签；右边用一个子框架把输入控件“抱”在一起
        ttk.Label(frm, text="增温步长(Δt):").grid(row=3, column=0, sticky='e')

        param = ttk.Frame(frm)
        param.grid(row=3, column=1, columnspan=3, sticky='w')  # 占后面3列，但整体靠左

        step_entry = ttk.Entry(param, textvariable=self.step, width=10)
        step_entry.pack(side='left')

        ttk.Label(param, text="  小数位：").pack(side='left', padx=(8, 4))  # 给点左右间距
        sp = ttk.Spinbox(param, from_=0, to=6, textvariable=self.rounding, width=5)
        sp.pack(side='left')
        frm.columnconfigure(1, weight=1)
        # 动作按钮
        btnfrm = ttk.Frame(self)
        btnfrm.pack(fill='x', **pad)
        ttk.Button(btnfrm, text="开始匹配并导出", command=self.start_process).pack(side='left')
        ttk.Button(btnfrm, text="清空预览", command=self.clear_preview).pack(side='left', padx=8)

        # 预览表
        self.tree = ttk.Treeview(self, columns=("c1","c2","c3","c4","c5"), show='headings', height=12)
        self.tree.pack(fill='both', expand=True, padx=8, pady=6)

        # 日志
        self.log = tk.Text(self, height=6)
        self.log.pack(fill='x', padx=8, pady=6)
        self.log_insert("就绪。请选择IR时间(s)与TG时间(s)，然后点击“开始匹配并导出”。\n")

        # 列宽
        for col, title, width in zip(("c1","c2","c3","c4","c5"),
                                     ('T1_Secs','T2_Min','Matched_T3_Min','Raw_Temperature','Final_Temperature'),
                                     (100,120,140,150,150)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor='center')

        self.columnconfigure(0, weight=1)

    # ---------- 事件处理 ----------
    def choose_t1(self):
        path = filedialog.askopenfilename(
            title="选择 IR时间(s) 文件",
            filetypes=[("文本文件", "*.txt;*.log;*.csv;*.dat;*.lst;*.tsv"), ("所有文件", "*.*")]
        )
        if path:
            self.t1_path.set(path)

    def choose_stad(self):
        path = filedialog.askopenfilename(
            title="选择TG时间(s)（含 Time(min) 与 Temperature）",
            filetypes=[("文本文件", "*.txt;*.stad;*.csv;*.dat;*.tsv;*.log"), ("所有文件", "*.*")]
        )
        if path:
            self.stad_path.set(path)

    def choose_out(self):
        path = filedialog.asksaveasfilename(
            title="保存结果 CSV",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")]
        )
        if path:
            self.out_path.set(path)

    def start_process(self):
        t1 = self.t1_path.get().strip()
        stad = self.stad_path.get().strip()
        outp = self.out_path.get().strip()
        step = self.step.get().strip()
        rounding = self.rounding.get()

        if not t1 or not os.path.isfile(t1):
            messagebox.showwarning("提示", "请先选择有效的 IR时间(s) 文件。")
            return
        if not stad or not os.path.isfile(stad):
            messagebox.showwarning("提示", "请先选择有效的TG时间(s)。")
            return
        if not outp:
            # 默认放在 T1 同目录
            outp = os.path.join(os.path.dirname(t1), "result.csv")
            self.out_path.set(outp)

        # 防止 UI 卡顿，放到线程里
        th = threading.Thread(target=self._run_process_thread, args=(t1, stad, outp, step, rounding), daemon=True)
        th.start()

    def _run_process_thread(self, t1, stad, outp, step, rounding):
        try:
            header, rows, saved = process_match(t1, stad, outp, float(step), int(rounding))
            self.log_insert(f"处理完成，结果已保存：{saved}\n")
            self.preview_rows(header, rows[:200])  # 预览最多 200 行，避免卡界面
            try:
                # 尝试选中并滚动到第一行
                if rows:
                    self.tree.selection_set(self.tree.get_children()[0])
                    self.tree.see(self.tree.get_children()[0])
            except Exception:
                pass
        except Exception as e:
            self.log_insert(f"[错误] {e}\n")
            messagebox.showerror("错误", str(e))

    def preview_rows(self, header, rows):
        self.clear_preview()
        # 重设表头（以防自定义列名变更）
        cols = ("c1","c2","c3","c4","c5")
        for col, title in zip(cols, header):
            self.tree.heading(col, text=title)

        for r in rows:
            self.tree.insert("", "end", values=[str(x) for x in r])

    def clear_preview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def log_insert(self, msg: str):
        self.log.insert('end', msg)
        self.log.see('end')


if __name__ == "__main__":
    App().mainloop()
