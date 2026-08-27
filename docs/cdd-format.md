# CDD 文件结构与公共工具

`.cdd` 是 XML。本文讲解析器实际用到的那部分结构、`cdd_parser_shared.py` 提供的公共
工具，以及几条**跨解析器共通的坑**——单个解析器特有的坑写在 [parsers.md](parsers.md)。

## 1. 顶层骨架

```
CANDELA
└─ ECUDOC                     ← 所有解析器的入口元素
   ├─ DATATYPES               ┐
   ├─ DIDS                    │ 文档级共享定义
   ├─ RECORDDTPOOL            │ （不在任何 VAR 之下）
   ├─ RECORDTMPLS             │
   ├─ DCLTMPLS                │
   ├─ DEFATTS / ATTRCAT       │
   ├─ STATEGROUPS             ┘
   └─ ECU
      ├─ NAME/TUV, QUAL
      ├─ UNS / ENUM / CSTR    ← ECU 层的属性取值（覆盖定义默认值）
      └─ VAR                  ← 一个或多个 variant
         ├─ NAME/TUV, QUAL
         ├─ DIDREFS/DIDREF    ← 「这个 DID 在本 variant 里存在」
         ├─ DIAGCLASS         ← 勾选的诊断类（多实例）
         │  └─ DIAGINST       ←   类下的各个实例
         └─ DIAGINST          ← 勾选的诊断类（singleton，直接是实例）
```

## 2. 最重要的一条模式：文档级定义 + variant 引用

**几乎所有内容都是「本体存在文档级、variant 只放一份引用」**。数据类型、DID、DTC、
诊断类全是这个模式：

| 本体（文档级） | variant 侧的引用 | 对应概念 |
|---|---|---|
| `DATATYPES` 下的类型元素 | 各处 `@dtref` | 数据类型 |
| `DIDS/DID` | `VAR/DIDREFS/DIDREF@didRef` | 该 DID 在每个 variant 里存在与否 |
| `RECORDDTPOOL/RECORD` | 别处的 `RECORDREF@idref` | 故障码 |
| `DCLTMPLS/DCLTMPL` | `VAR` 下 `DIAGCLASS`/`DIAGINST@tmplref` | 该 variant 启用了哪些诊断类 |

两个直接后果，**看错了就会整块解析错**：

1. **「使能」不是一个布尔字段**，而是「这个 variant 里有没有这个对象的实体」。
   文件里没有任何 `enabled`/`checked` 之类的属性可读——**有实体就是启用，删掉实体
   就是不启用**。所以判断某个 variant 支持哪些诊断类，只能去数它下面挂了哪些实体。
2. **「存在」和「被使用」是两件事**。DID 和 DTC 都有 `used` 字段：前者靠
   `VAR/DIDREFS/DIDREF` 表示存在，靠 `DIDREFS` **之外**的 `DIDREF`/`DIDDATAREF`
   表示被某个服务真正读写。`CddTools.cdd` 里 16 个 DID 有 2 个（`0xFF00`/`0xFF01`）
   存在但没被任何服务用到。

## 3. 引用怎么解

CDD 里的引用属性名有一大把——`tmplref`、`dtref`、`idref`、`didRef`、`attrref`、
`shstaticref`、`shproxyref`、`attrcatref`——但**目标都靠全局唯一的 `@id` 定位**。
所以任何解析器的第一步都是建 id 索引：

```python
shared = CddParserShared()
shared.build_id_index(ecu_doc)   # 遍历所有带 @id 的元素，建 id → element 字典
element = shared.by_id(some_ref)
```

`load_ecu_doc()` 已经把「解析 XML → 找到 `ECUDOC` → 建索引」打包成一行，日常直接用它。

## 4. `CddParserShared` 提供的东西

| 方法 | 作用 |
|---|---|
| `build_id_index(root)` / `by_id(id)` | id 索引，见 §3 |
| `direct_children(el, tag=None)` | 只取**直接**子元素，可按 tag 过滤 |
| `first_child(el, tag)` | 第一个匹配 tag 的直接子元素 |
| `find_first_by_path(el, path)` | 按 `/` 逐层下钻 |
| `text_by_path(el, path)` | 取路径目标的文本并 strip，空串视作 `None` |
| `name(el)` / `qual(el)` | `NAME/TUV` 回退 `QUAL` / `QUAL` 回退名字 |
| `hex_value(v)` | 十进制字符串 → `0x{:02X}`，失败原样返回 |
| `text_map_values(tbl)` | `TEXTTBL` 下各 `TEXTMAP` 的 `@s`/`@e` + `TEXT/TUV` |
| `member(el)` / `member_list(el)` | Member / Gap / Struct 成员树，见 §5 |
| `data_type_summary(dt)` | 数据类型的简要摘要 |

**只取直接子元素这件事很关键**。CDD 大量嵌套同名标签，用 `iter()` 会把嵌套层里的
元素一起捞出来——比如数诊断类时，`DIAGCLASS` 里嵌的 `DIAGINST` 是「那个类的实例」，
不是「另一个被勾选的类」，只能数 `VAR` 的直接子节点。

## 5. 成员树：Member / Gap / Struct

数据类型的 `STRUCTDT`/`MUXDT`/`EOSITERDT`、DID 的 `STRUCTURE`、电报的参数容器，
用的是**同一套成员结构**，所以由 `member_list()` 统一处理，三种 type：

| type | 来自 | 带的字段 |
|---|---|---|
| `Member` | `DATAOBJ` / `SPECDATAOBJ` | `dtref`、`dtQual`、`description`、`default`(`@def`)、`staticValue`(`@v`) |
| `Gap` | `GAPDATAOBJ`（保留位） | `bitLength`(`@bl`) |
| `Struct` | `STRUCT`（把一个字节拆成若干位域） | `dtref` + 递归的 `members` |

`STRUCTDT` 实测有两种排列，都要处理：多数直接挂 `DATAOBJ`；需要位域时才包一层
`STRUCT`，`STRUCT` 自身既是一个成员、又嵌套自己的子成员。

## 6. 值类型：`CVALUETYPE` / `PVALUETYPE`

编码信息挂在这两个元素的属性上，coded 是总线上的原始值，physical 是物理值：

| 属性 | 含义 | 取值 |
|---|---|---|
| `@bl` | 位长 | 见下方「`qty=field` 的坑」 |
| `@bo` | 字节序 | `12` = LowHigh (Intel)，`21` = HighLow (Motorola) |
| `@enc` | 编码 | `uns`/`sgn`/`utf`/`asc`/`dbl`/`flt`/`bcd` |
| `@sig` | **Precision（浮点小数位数）** | 见下方警告 |
| `@df` | 显示格式 | `dec`/`hex`/`text`/`flt` |
| `@qty` | 数量 | `atom`（单值）/ `field`（数组），后者带 `@minsz`/`@maxsz` |

> **`@sig` 不是「有无符号」。** 这个属性一度被误判成 signed 标志。实测它在 `dbl`/`flt`
> 编码下取值 0~8 且分布分散，和 `enc` 的 `uns`/`sgn` 完全不相关——它是 Properties
> **Precision**（浮点小数位数）。有无符号已经由 `@enc` 表达，别再从这个字段猜。

> **`qty="field"` 时 `@bl` 是单个元素的宽度，不是总宽度。** 总位宽要乘以元素个数
> （`@minsz`/`@maxsz`）。算电报字节位置时按 `@bl` 直接累加，会把四个 16 字节的参数
> 排到 byte 0/1/2/3 而不是 0/16/32/48。

## 7. 枚举必须读标签文本，不能读数值

`ENUMDEF` 下的 `ETAG@v` → `TUV` 是取值到文字的映射。**同一个数值在不同文档、不同
接口下含义可以完全不同**——`CddTools.cdd` 里 `CAN` 和 `CAN_Extended_Addressing` 的
`AddrScheme` 存着各自的数值，标签却分别是 `Normal` 和 `Extended`；`CanIdType` 也是
一样，按数值判断会把 11-Bit 和 29-Bit 混为一谈。

**凡是判断「这是什么」的地方，一律读标签文本**：寻址方式、CAN-ID 类型、CAN FD 开关、
DTC 的枚举属性列，全都如此。同理，接口名、DTC 属性列名也都是每份文档自定义的，
得从文档里读出来，不能按名字硬编码。

## 8. 有些显示内容根本不在文件里

工具里看到的字符串，未必存在于 `.cdd`：

- **DTC 显示码**（`P0100` 这种）是从一个 24 位整数按 SAE J2012 实时算出来的。
  直接搜字符串搜不到，算法见 [parsers.md](parsers.md#3-dtcs)。
- **报文 payload 占位符**（`zz`、`yy`）是编辑器显示时现生成的，全文搜
  `zz`/`yy` 命中数为 0，同一个服务在不同文档里字母还不一样。本项目统一输出 `..`，
  不去猜那个算法。唯一稳定的是响应码占位符 `rc`（`dest="resCode"`），照原样输出。

原则一句话：**读文档，不读显示名。**
