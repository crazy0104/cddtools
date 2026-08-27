# cdd_viewer：只读图形界面

`cddtools/cdd_viewer.py` 是一个只读的 tkinter GUI，八个 tab，每个 tab 能单独导出
JSON。

> 窗口已在真实桌面环境跑过。此外 §6 那几个不依赖 tkinter 控件的纯逻辑函数有自动化
> 覆盖：把 `tkinter`/`ttk`/`filedialog`/`messagebox` 换成占位实现后，八个 tab 在
> `CddTools.cdd` 上都不报错、列数与表头数量对得上。

## 1. 怎么运行

```bash
python -m cddtools.cdd_viewer
```

或者：

```python
from cddtools.cdd_viewer import CddViewer

CddViewer().mainloop()
```

默认加载 `examples/CddTools.cdd`；找不到就跳过，不弹窗，只在状态栏提示。

## 2. 界面结构

```
┌─────────────────────────────────────────────────────────────┐
│ [Open CDD]  <当前文件路径>                                    │  ← 工具栏
├──────────────────────────────┬──────────────────────────────┤
│ [Interfaces][Diagnostic Classes][Supported Services]         │
│ [Data Types][DIDs][DTCs][DTC Status][States]                 │
│  ┌────────────────────────┐  │   选中行的完整 JSON            │
│  │ 名字 | 列... (Treeview) │  │   （只读 Text，不可编辑）      │
│  └────────────────────────┘  │                              │
│  [Export Data Types as JSON…]│                              │  ← 每个 tab 自己的按钮
├──────────────────────────────┴──────────────────────────────┤
│ 状态栏：已加载 N 条 / 导出结果                                 │
└─────────────────────────────────────────────────────────────┘
```

tab 顺序就是上图的顺序，`Interfaces` 在最前——它是最便宜的一个 tab，窗口不用等大段
Data Types 解析完就能出来。

- **Open CDD**：`filedialog.askopenfilename` 选文件，重新加载并清空八个 tab 的缓存。
- **懒加载**：某个 tab 第一次被切换到时才调对应的 parser（`_populate_tab`），结果缓存
  在 `self._entries[tab]`，切回去不重新解析。避免打开数据类型上万条的大文件时八个
  tab 一次性全解析卡住界面。
- 选中一行 → 右侧 Text 显示这一条的完整 JSON。
- 每个 Treeview 和右侧详情都配了横向 + 纵向滚动条；列都设了 `stretch=False`，宽度固定，
  不会被窗口挤压变形，超出可见区域靠横向滚动条看而不是被截断。

## 3. 只读性

- Treeview 没有绑定任何双击编辑 / 右键菜单 / 拖拽排序，纯展示。
- 右侧详情 `Text` 常态是 `state="disabled"`，插入内容前临时切 `"normal"`、插完立刻
  切回，用户没法在框里敲字。
- 不写回 `.cdd`、不修改内存里的解析结果，唯一的输出动作是导出 JSON 到新文件。

## 4. 各 tab 的列

| Tab | 树列（#0） | 附加列 |
|---|---|---|
| Interfaces | `✓ 接口名`（可展开） | Type, Category, Display, Default Value, Overwritten Value, Description |
| Diagnostic Classes | Class | Qual, Enabled, Singleton, Kind，**外加每个 variant 一列** |
| Supported Services | Variant / Class / Instance（可展开） | Id / Bytes / Byte No., Qual, Data Type / Protocol Service, Default / Constant |
| Data Types | Name | Qual, Conversion, Bit Length, Bitmask |
| DIDs | Name | Qual, Identifier, Used, DID Data |
| DTCs | DTC（显示码，如 `P0100`） | Failure Type, Failure Type Text, Used, Error Text |
| DTC Status | Bit | Mask, Supported, Definition, Qual |
| States | State Group / State（可展开） | Qual, Kind, Description |

三个 tab 值得单独说明：

**Interfaces**：顶层一行一个接口，展开是它的通信参数。**列出文档定义的全部接口，
行首 ✓ 标记 ECU 实际支持的那些**——模板常会提供 CAN FD、DoIP 等这个 ECU 并未选用的
接口，看 ✓ 才知道哪个真正生效。**只显示接口参数**，其余分类（ODX / Editor / Autosar /
CANdesc / Quality Management…）不进这个 tab；要全量属性走 API 的
`parse_attributes()`。

**Supported Services** 是树：实例节点下挂服务（再下挂 Request / Pos. Resp. /
Neg. Resp. 三行报文）和电报表格（再下挂各参数行）。四个列在不同层级复用——实例行显示
标识符 / Qual / Protocol Service；报文行第一列是字节序列（如 `10 01`）；电报参数行
第一列是 `字节号[.位号]`，第三列是数据类型，第四列是 Default / Constant。选中任意
一层，右侧都显示那一层对应的完整 JSON。

**Diagnostic Classes** 的 variant 列是**动态**的：variant 的数量和名字因文档而异
（`CddTools.cdd` 只有一个 `Base_Variant`），所以这些列只能在解析出结果之后才建得出来，
由 `_apply_variant_columns()` 在 `_populate_tab()` 里重新配置 Treeview 的 `columns`。

右侧详情面板永远是这一行**完整**的解析结果（parser 输出的原始 dict，未做任何列裁剪），
所以列表里只挑了几个常用字段当预览，其余（Data Types 的 `codedValue`/`textTable`/
`members`、DID 的 `data`、DTC 的 `properties`）都在详情里看。

## 5. 导出

每个 tab 底部都有自己的 **"Export `<Tab>` as JSON…"** 按钮（`export_tab(tab)`），
只导出这一个 tab 的完整数据，**和当前切换到哪个 tab 无关**——按钮自带 tab 参数
（`command=lambda t=tab: self.export_tab(t)`），不需要先切过去。即使这个 tab 还没被
访问过、还没解析过，点导出也会先触发 `_populate_tab` 解析一次再导出。默认文件名
`{cdd文件名}_{tab名}.json`（如 `CddTools_dids.json`）。

## 6. 不依赖 tkinter 实例的函数

这几个函数不碰任何控件，把 `tkinter`/`ttk`/`filedialog`/`messagebox` 换成占位模块后
可以直接单测，无需桌面环境：

- `load_ecu_doc(file_path)` —— 解析 XML、定位 `ECUDOC`、建好 id 索引，返回
  `(shared, ecu_doc)`。
- `parse_tab(tab, shared, ecu_doc)` —— 按 tab 名派发到对应的解析器。
- `row_for_entry(tab, entry, extra_columns=())` —— 把一条 parser 输出转成
  `(树列文本, 附加列元组)`。`extra_columns` 只对 Diagnostic Classes 有意义，传入
  variant qual 列表，为每个 variant 追加一个 yes/- 单元格。
- `interface_parameter_rows(interface)` —— 把一个接口的通信参数摊平成子行；
  `Overwritten Value` 列只在 `source != "default"` 时才填。
- `state_rows(group)` —— 把一个状态组的各状态摊平成子行。
- `service_tree_rows(entry)` —— 把一个诊断实例摊平成 `(文本, 列值, 数据, 子行)`
  四元组，供递归插入 Treeview。
- `variant_quals(entries)` —— 从 Diagnostic Classes 的结果里取出动态列的表头。
