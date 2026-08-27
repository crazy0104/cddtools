# 解析器

每个 `cdd_*_parser` 负责 `.cdd` 里的一块内容，目标是**如实读出文件里写了什么**，
不做加工也不做推断。

先读 [cdd-format.md](cdd-format.md)：取名字规则、id 索引、成员树、`CVALUETYPE` 属性、
「文档级定义 + variant 引用」模式这些是共通的，本文不再重复。跑法见
[usage.md](usage.md)。

| 内容 | 模块 | 入口 |
|---|---|---|
| 数据类型 `DATATYPES` | `cdd_datatypes_parser` | `CddDataTypesParser.parse(ecu_doc)` |
| DID `DIDS` | `cdd_did_parser` | `CddDidParser.parse(ecu_doc)` |
| 故障码 `RECORDDTPOOL` | `cdd_dtc_parser` | `CddDtcParser.parse(ecu_doc)` |
| DTC 状态字节 `DTCSTATUSMASK` | `cdd_dtc_parser` | `.parse_status_mask(ecu_doc)` |
| 诊断类 `DCLTMPLS` + 各 variant | `cdd_diagnostic_classes_parser` | `.parse(ecu_doc)` |
| 诊断实例与服务 `DIAGINST` | `cdd_services_parser` | `CddServicesParser.parse(ecu_doc)` |
| 属性与接口 `DEFATTS` | `cdd_attributes_parser` | `.parse()` / `.parse_interfaces()` |
| 状态组 `STATEGROUPS` | `cdd_states_parser` | `CddStatesParser.parse(ecu_doc)` |

以下所有「实测」数字都出自 `examples/CddTools.cdd`。

---

## 1. Data Types

解析 `DATATYPES` 下的全部数据类型：种类、编解码属性、文本表 / 线性换算、成员结构、
无效值，以及挂在类型上的属性值。

数据类型元素的**标签本身就是种类**，对应 Conversion 概念：

| 标签 | Conversion | 实测条数 |
|---|---|---|
| `TEXTTBL` | Text Table | 54 |
| `IDENT` | Raw value | 43 |
| `STRUCTDT` | Packet | 3 |
| `MUXDT` | Mux | 2 |
| `COMPTBL` | Piecewise Linear | 2 |
| `LINCOMP` | Linear | 3 |
| `VALTBL` | Characteristic Curve | 1 |
| `PROCDT` | Procedural Conversion | 1 |
| `FORMULADT` | Formula | 1 |
| `STATICITERRDT` | Fixed Count Iteration | 1 |
| `NUMITERDT` | Counter Iteration | 1 |
| `ENDMKITERDT` | End-Marker Iteration | 1 |
| `EOSITERDT` | End-of-Service Iteration | 1 |

样本文件覆盖了 CANdelaStudio 提供的全部 13 种数据类型。四种迭代类型默认被
文档的 `ECUDOC@xdtauth` 位掩码禁止创建（`30` = 禁止第 1–4 位，即四种迭代），
需要在 `File | Properties | Data Type Authorization` 里放开——这也是为什么它们
在实际工程的 CDD 里几乎不出现。

### 字段

| 解析目标 | CDD 字段 | 说明 |
|---|---|---|
| kind / conversion | 元素自身的 tag | 见上表 |
| bitLength | `CVALUETYPE@bl`、`@qty` | `atom` → `"字节:位"`；`field` 且 `minsz==maxsz` → `"[N]"`；否则 `"[min..max]"` |
| bitmask | 元素 `@bm` | 转 `0x..` |
| codedValue / physicalValue | `CVALUETYPE` / `PVALUETYPE` 的属性 + 子 `UNIT` | 属性含义见 [cdd-format.md §6](cdd-format.md#6-值类型cvaluetype--pvaluetype) |
| textTable | `TEXTMAP@s/@e` + `TEXT/TUV` + `ADDINFO/TUV` | 仅 `TEXTTBL` |
| linear | `COMP@f`(factor) `@o`(offset) `@s/@e`(生效区间) | 仅 `LINCOMP` |
| interpolated | 元素 `@interpolated` | 仅 `VALTBL`，区分特性曲线是否插值 |
| formula | 子 `FORMULA@usage` + 元素文本 | 仅 `FORMULADT`，`usage` 为 `coded2Phys`/`phys2Coded` |
| procedure | 子 `PROCCONV/FUNCTION@usage/@jobFileRef/@entryPoint` | 仅 `PROCDT` |
| numOfItems | 元素 `@numOfItems` | 仅 `STATICITERRDT`，唯一把重复次数存在文件里的迭代类型 |
| members | 直接子 `DATAOBJ`/`GAPDATAOBJ`/`SPECDATAOBJ`/`STRUCT` | 仅 `STRUCTDT`/`EOSITERDT` |
| mux | 见 §1.1 | 仅 `MUXDT` |
| invalidValues | `EXCL@s/@e/@inv` | Invalid Values 页签 |
| attributes | 子 `ENUM`/`CSTR` 的 `@attrref` 反查定义 | Attributes 页签 |
| minNumOfItems | `EOSITERDT@minNumOfItems` | 仅 End-of-Service Iteration |

`codedValue`/`physicalValue` 展开后是
`{bitLength, byteOrder, encoding, precision, displayFormat, quantity, [minSize, maxSize, unit]}`。

### 1.1 Mux 的结构和 Packet 不一样

`MUXDT` 不能套用「直接子 `DATAOBJ`」那一套：

- `MUXDT@dtref` 是**选择器**的数据类型（通常是个 `TEXTTBL`），对应对话框里的
  "Selector Data Object for Multiplexer"。
- 直接子 `STRUCTURE` 是**默认分支**的成员列表（选择器不匹配任何 case 时用）。
- 每个 `CASE@s/@e` 是一个分支，其下同样包一个 `STRUCTURE`。

输出 `{selectorDtref, selectorDtQual, default: [...], cases: [{start, end, members}]}`。
实测样本：`Memory_Address_and_Size`（选择器是 `AddressAndLengthFormatIdentifier`，
变长 `[2..9]`）。

### 1.2 Attributes 页签

类型元素下的 `ENUM`/`CSTR` 是「属性取值实例」，`@attrref` 指向 `DATATYPEATTS` 里的
`ENUMDEF`/`CSTRDEF`。枚举取值要读 `ETAG` 文本（见
[cdd-format.md §7](cdd-format.md#7-枚举必须读标签文本不能读数值)）。

对话框里的 Authorization 页签**未实现**：那是模板（`DCLTMPL`）级的权限设置，不落在
单个数据类型节点上。

### 输出

```
Entry { id, name, qual, description, kind, conversion, bitLength, bitmask,
        codedValue, physicalValue,
        invalidValues: [{start, end, invalidType}],
        attributes: [{name, qual, value}],
        textTable | linear | members | mux | minNumOfItems }   # 按 kind 才有
```

代表样本：`ASCII_17_Bytes`（定长字段 `[17]`）、`Communication_Type`（Packet，含位域
`STRUCT` 与保留位 `GAPDATAOBJ`）、`DataIdentifier`（Text Table，含取值区间与
ADDINFO）、`CAN_Protocols_Supported_1Byte`（含无效值）、`P2Ex`（Linear，factor 10、
单位 ms）。

---

## 2. DIDs

解析 `DIDS` 下的全部 DID：标识符、数据结构，以及每个 variant 里是否存在、是否被
某个服务真正用到。

```
ECUDOC
├─ DIDS                      ← 文档级本体
│  └─ DID@id @n(=十进制 identifier)
│     ├─ NAME/TUV, QUAL
│     └─ STRUCTURE           ← DID Data，成员结构同 cdd-format.md §5
└─ ECU/VAR/DIDREFS/DIDREF@didRef   ← 「本 variant 里存在」
```

### 字段

| 解析目标 | CDD 字段 | 说明 |
|---|---|---|
| identifier / identifierHex | `DID@n`（十进制） | hex 格式化为 `0x{:04X}`（4 位大写） |
| variants | 各 `VAR/DIDREFS/DIDREF@didRef` 是否含该 `DID@id` | `{variant qual: bool}`，对应每 variant 一列 yes/no |
| used | 该 id 是否被 `DIDREFS` **之外**的 `DIDDATAREF`/`DIDREF` 引用 | 对应 Used 列，见下 |
| data | `STRUCTURE` 下成员，复用 `member_list()` | |
| dataSummary | 由 `data` 生成的逗号分隔串 | 对应 DID Data 列 |

### `used` 的判定

散落在 `SERVICE`/`REQ`/`POS`/`NEG` 里的两种引用才算「被用到」，它们和
`VAR/DIDREFS/DIDREF` 只是恰好标签同名：

- `DIDDATAREF@didRef` —— "DID Data Reference"，只代表数据部分。
- `DIDREF@didRef`（出现在 `DIDREFS` 之外）—— "DID Reference"，identifier + 数据。

实现上遍历全文档，检查每个元素的**直接子节点**；元素本身是 `DIDREFS` 就跳过，避免把
「variant 存在性」误算成「被使用」。实测 16 个 DID 里 `0xFF00`、`0xFF01` 两个
`used=false`。

### `dataSummary` 拼接规则

`Member` 直接用 `name`；`Struct` 渲染成 `名字(子项1, 子项2)`；`Gap` 整项跳过。
实测 16 个 DID 的数据都是纯 `DATAOBJ`，**`Struct` 分支缺样本验证**——位域子项加括号
这个渲染规则是按结构推的，没有样本兜底。

### 输出

```
DidEntry { id, identifier, identifierHex, name, qual,
           variants: {variantQual: bool}, used: bool,
           data: [Member|Gap|Struct], dataSummary: str }
```

---

## 3. DTCs

解析 `RECORDDTPOOL` 下的 24 位故障码池（同级还有一个 16 位 OBD 池，样本里是空的）：
显示码、失效类型、错误文本，以及模板定义的自定义属性列。

```
ECUDOC
├─ RECORDTMPLS/RECORDTMPL@spec='faultMemory'   ← 每条 DTC 有哪些自定义列
│  ├─ ENUMRECORDITEMTMPL@id                    ←   枚举列，ETAG@v → 取值文字
│  └─ TRRECORDITEMTMPL@id                      ←   文本列，DEFAULT 是默认文案
├─ DATATYPES/TEXTTBL[QUAL='SAE_J2012_Failure_Type_Byte']  ← 失效类型字节 → 文字
└─ RECORDDTPOOL/RECORDDT@rtSpec='faultMemory'
   └─ RECORD@id @v          ← 24 位原始整数：高 16 位 = DTC 号，低 8 位 = 失效类型字节
      ├─ TEXT/TUV                    ← Error text
      ├─ ENUMRECORDITEM@idref @v     ← 枚举列取值
      └─ TRRECORDITEM@idref + TEXT/TUV
```

另有一个不带 `rtSpec` 的 `RECORDDT`（普通数据类型，会被诊断实例引用），里面用
`RECORDREF@idref` 列出实际用到的 `RECORD`——这是 `used` 的依据，模式和 DID 一样。

### 显示码怎么算：`_format_dtc(raw16)`

**`.cdd` 里搜不到 `P0100` 这样的字符串**，显示码是按 SAE J2012 / ISO 15031-6 的
5 字符格式（1 个类别字母 + 4 位十六进制）实时算出来的：

1. `raw16` = 24 位原始值的高 16 位（`raw >> 8`）。
2. 类别字母 = `raw16` 最高 2 位（`(raw16 >> 14) & 0b11`）映射 `"PCBU"`
   （0=P 动力总成、1=C 底盘、2=B 车身、3=U 网络）。
3. 4 位十六进制码 = `raw16 & 0x3FFF`（低 14 位），格式化为 `{:04X}`。

低 8 位（`raw & 0xFF`）是失效类型字节，查全局 `SAE_J2012_Failure_Type_Byte` 文本表
得到 "Failure type text" 列。

实测：`RECORD@v='65559'`（`0x010017`）→ `raw16=0x0100`，类别位 `00`=P，
`0x0100 & 0x3FFF = 0x0100` → **P0100**；低字节 `0x17` 查表 → "Circuit Voltage Above
Threshold"。4 条 DTC 全部按此公式验证通过。

### 自定义列是模板驱动的

`RECORDTMPL` 定义有哪些列，**不同文档的列名不同**，所以 `properties` 是动态 dict
（key 是列的 `NAME/TUV`），**不要按名字硬编码取值**。两种列：

- `ENUMRECORDITEMTMPL` ↔ `RECORD` 里的 `ENUMRECORDITEM@idref @v`：下拉枚举，
  文字来自模板的 `ETAG@v`/`TUV`。
- `TRRECORDITEMTMPL` ↔ `TRRECORDITEM@idref` + 自带 `TEXT/TUV`：自由文本，模板只给
  默认文案。

实测这份文档给出 6 列：Corrective action、Aging Supported、Aging Cycle Counter
Threshold、DTC Priority、DTC Severity、Functional Unit。

另有 "SYNCHELEMENT" 和 "Vehicle System Groups" 两项，样本里没有数据，**未实现**
（不确定对应哪个 XML 字段）。

### DTC 状态字节：`parse_status_mask()`

单独一个入口，解析 `DTCSTATUSMASK`，给出 ISO 14229-1 的 8 个位：位号、掩码、名字、
qual、该位是否被这个 ECU 实现，以及合成的 `supportedMask`。

### 输出

```
DtcEntry { id, dtc, raw, failureType, failureTypeText, errorText,
           used: bool, properties: {列名: 值} }

StatusMask { name, qual, bitLength, supportedMask,
             bits: [{bit, mask, name, qual, support, supported, dtref}] }
```

实测 4 个 DTC（`P0100`/`P0101`/`U1174`/`U1527`），全部 `used=true`——**`used=false`
分支缺样本验证**，不像 DID 那样有真实反例兜底。

---

## 4. Diagnostic Classes

解析文档定义了哪些诊断类，以及每个 variant 启用了其中哪些。

这两件事在文件里是分开存的（模式见
[cdd-format.md §2](cdd-format.md#2-最重要的一条模式文档级定义--variant-引用)）：
整个复选框列表来自文档级的 `DCLTMPLS/DCLTMPL`，哪些被勾上来自各 `VAR` 下有没有
`@tmplref` 指向该模板的实体。

### singleton：勾选可能是 `DIAGCLASS` 也可能是 `DIAGINST`

`DCLTMPL@single` 决定这个类在 variant 里以什么形式存在：

- `single='1'`（singleton，如 Tester Present、Control DTC Setting）→ variant 里直接
  挂一个 **`DIAGINST`**，树上是叶子。
- `single='0'`（多实例，如 Sessions、Security Access）→ variant 里挂一个
  **`DIAGCLASS`**，里面再包若干 `DIAGINST`，树上是可展开节点。

实测这个对应关系**严格一一对应**：`DIAGCLASS`+`single='0'` 14 次，
`DIAGINST`+`single='1'` 5 次，混搭 0 次。所以两种标签都得认——**只认 `DIAGCLASS`
会漏掉全部 singleton**。

### 字段

| 解析目标 | CDD 字段 | 说明 |
|---|---|---|
| classKind | `DCLTMPL@cls` | 内部用例代码（`ses`/`ftm`/`tpr`/`sec`/`com`/`fun`…），**原样透出不映射**——没有可靠依据把它们翻成显示名，不猜 |
| singleton | `DCLTMPL@single == '1'` | 见上 |
| variants | 各 `VAR` 的**直接子** `DIAGCLASS`/`DIAGINST@tmplref` 是否命中 | `{variant qual: bool}`，对应复选框 |
| instanceCounts | `DIAGINST` 个数（`DIAGCLASS` 数其子节点，裸 `DIAGINST` 记 1） | 未勾选为 0 |
| enabled | `any(variants.values())` | 多 variant 时是**并集** |

输出顺序保持 `DCLTMPLS` 的文档顺序，可以和文件逐条对齐。

### 输出

```
ClassEntry { id, name, qual, description, classKind, singleton: bool,
             variants: {variantQual: bool}, instanceCounts: {variantQual: int},
             enabled: bool }
```

实测 30 个类，`Base_Variant` 勾选 19 个，11 个是 singleton。前几行：

```
[x]  Sessions                       cls=ses  实例=3
[x]  Ecu Reset                      cls=fun  实例=2
[x]  Security Access                cls=sec  实例=2
[x]  Communication Control          cls=com  实例=4
[ ]  Communication Control - Enh…   cls=com  实例=0
[x]S Tester Present                 cls=tpr  实例=1
[x]S Control DTC Setting            cls=fun  实例=1
```

> 要看某一个 variant 的启用情况就取 `variants[<该 variant 的 qual>]`，别用 `enabled`
> （那是并集）。`CddTools.cdd` 只有一个 variant，两者等价。

---

## 5. Services（Diagnostic Instance）

解析每个诊断实例：名字、标识符、它用的服务和协议服务，请求 / 正响应 / 负响应的
报文格式，以及电报里每个参数的字节位置、数据类型、默认值与常量值。

上一层「哪些类被启用」见 §4；本解析器往下钻一层，解析每个类里的实例和它们的服务。

### 5.1 要跟三条引用链

一个实例的信息分散在「模板」和「实例」两侧：

**① 报文骨架**：`DIAGINST/SERVICE@tmplref` → `DCLSRVTMPL@tmplref` → `PROTOCOLSERVICE`

`PROTOCOLSERVICE` 下的 `REQ`/`POS`/`NEG` 才是报文格式的来源，由整个类共享。以
`($10) DiagnosticSessionControl` 为例：

```
REQ: CONSTCOMP(spec=sid, v=16)  STATICCOMP(spec=sub)
POS: CONSTCOMP(spec=sid, v=80)  STATICCOMP(spec=sub)  SIMPLEPROXYCOMP(dest=data)
NEG: CONSTCOMP(spec=sid, v=127) CONSTCOMP(spec=sid, v=16) SIMPLEPROXYCOMP(dest=resCode)
```

拼出来就是 `10 01` / `50 01 ..` / `7F 10 rc`。

**② 子功能字节**：`STATICCOMP@id` → 类模板 `SHSTATIC/STATICCOMPREF@idref` → 实例
`STATICVALUE@shstaticref` 的 `@v`

这条链把泛化的子功能槽位变成具体实例的值。三个 Session 实例共享同一份
`PROTOCOLSERVICE`，靠这条链分别得到 `10 01`、`10 02`、`10 03`。

**③ 电报表格**：proxy 组件 `@id` → 类模板 `SHPROXY/PROXYCOMPREF@idref` → 实例
`SIMPLECOMPCONT@shproxyref`

容器里的 `DATAOBJ` 就是表格的行。它挂在 `DIAGINST` 上而不是模板上，所以同名电报在
不同实例、不同 variant 里内容可以完全不同。

### 5.2 字节序列的拼法

| 组件 | 渲染 |
|---|---|
| `CONSTCOMP` | `@v` 按 `@bl` 拆成大端字节，如 `v=16,bl=8` → `10` |
| `STATICCOMP` | 走链②取到的值，按**数据类型**的位宽拆字节 |
| proxy 类组件 | 占位符 `..`，响应码为 `rc`（原因见 [cdd-format.md §8](cdd-format.md#8-有些显示内容根本不在文件里)） |

**多字节标识符要拆开**：`Boot Software` 的标识符是 `0xF180`（2 字节 DID），必须渲染成
`22 F1 80` 而不是 `22 F180`。所以 `STATICCOMP` 的宽度取自 `@dtref` 指向的数据类型的
`CVALUETYPE@bl`，不能默认 8 位。

### 5.3 电报表格的行与字节位置

`byteNo`/`bitPos` 靠累加各成员数据类型的位宽得出——注意 `qty="field"` 时要乘元素个数
（见 [cdd-format.md §6](cdd-format.md#6-值类型cvaluetype--pvaluetype)）。`bitPos` 只在
非字节对齐时才给数字，对齐时为 `None`。

**`SPECDATAOBJ` 不是电报行**：容器里的 `SPECDATAOBJ` 是负响应码的容器而不是参数——
它没有 `@dtref`，子节点恰好是 `NAME`/`QUAL`/`NEGRESCODEPROXIES`。所以它被排除在
`TELEGRAM_MEMBER_TAGS` 之外，否则每个实例都会多出一个并不存在的电报条目。
（这和*数据类型* `STRUCT` 里的 `SPECDATAOBJ` 不是一回事，那个由 `member()` 处理。）

`Default` 列取 `@def`，`Constant` 列取 `@v`。

### 字段

| 解析目标 | CDD 字段 |
|---|---|
| variant / className / classQual | `VAR/QUAL`、`DIAGCLASS` 名字（singleton 时取 `DIAGINST@tmplref` 的模板名） |
| identifier | 实例只有一个 `STATICVALUE` 时取它 |
| staticValues | 全部 `STATICVALUE@shstaticref` → `SHSTATIC` 名字 → `@v` |
| services[].protocolService | 链①末端 `PROTOCOLSERVICE` 的名字 |
| services[].semantic | `SERVICE/SEMANTIC`，如 `SESSION` |
| request / positiveResponse / negativeResponse | `PROTOCOLSERVICE` 的 `REQ`/`POS`/`NEG` |
| components[].responseCodes | `dest="resCode"` 时，实例容器里 `NEGRESCODEPROXY@idref` → `NEGRESCODE` |
| telegrams[].parameters | 链③容器里的 `DATAOBJ`/`GAPDATAOBJ`/`STRUCT`/`DIDDATAREF`/`GODTCDATAOBJ`/`RECORDDATAOBJ`/`MUXDT` |

### 输出

```
InstanceEntry {
  id, variant, className, classQual, name, qual, description,
  identifier,                       # 单一静态值，如 "0x01"
  staticValues: {slotName: "0x01"},
  services: [{ name, qual, shortcutName, shortcutQual, semantic,
               protocolService, protocolServiceQual,
               request | positiveResponse | negativeResponse: {
                 name, qual, kind, bytes,
                 components: [{name, qual, kind, spec, role, bytes,
                               value?, dataType?, dest?, telegram?, responseCodes?}] } }],
  telegrams: [{ name, qual, kind, parameters: [
      {byteNo, bitPos, name, qual, kind, dataType, dataTypeQual,
       bitLength, constant, default, description}] }],
}
```

实测全文档 37 个诊断实例全部解析成功，没有悬空的 `tmplref`/`shstaticref`（有测试
守着）。`Sessions` 类的三个实例：

| 实例 | 标识符 | Request | Pos. Resp. | Neg. Resp. |
|---|---|---|---|---|
| Default Session | `0x01` | `10 01` | `50 01 ..` | `7F 10 rc` |
| Programming Session | `0x02` | `10 02` | `50 02 ..` | `7F 10 rc` |
| Extended Diagnostic Session | `0x03` | `10 03` | `50 03 ..` | `7F 10 rc` |

电报 `SessionParameterRecord`：`P2` @byte 0、`P2Ex` @byte 2（两个 16 位参数）。
多字节标识符：`Boot Software`（`0xF180`）的请求是 `22 F1 80`。

---

## 6. Attributes / Interfaces

解析 CDD 的属性机制：属性定义、各层取值覆盖，以及由它承载的接口与通信参数。

### 6.1 为什么覆盖面比「通信参数」宽

通信参数在文件里**没有自己独立的存储结构**——它们就是普通属性，和数据类型、DTC
上挂的那些属性走同一套机制。所以底层只有**一套 Attribute 机制**，通信参数只是它的
一种用法。机制分两半：

| | 位置 | 说明 |
|---|---|---|
| **定义** | `DEFATTS` 下的 `UNSDEF`/`SGNDEF`/`ENUMDEF`/`CSTRDEF`/`STRDEF` | 带 `QUAL`、`attrcatref`（指向 `ATTRCAT` 分类）、默认值 `@v` |
| **取值** | 对象上的 `UNS`/`SGN`/`ENUM`/`CSTR`/`STR`，用 `@attrref` 指回定义 | 覆盖该对象的默认值 |

实测文档里有 13 个 `ATTRCAT` 元素，其中 11 个真正被属性定义引用：Communication、
Timing、Available interfaces、UDS、ODX、Editor、Autosar、CANdesc、DEXT、
Quality Management、Any attribute category（`Initialization` 和一个重复的 `Autosar`
没有任何定义指向它们）。**统计分类数时按定义实际引用到的算，别数 `ATTRCAT` 元素个数。**
覆盖面这么宽，所以模块按 "Attribute" 命名而不是 "Communication Parameter"，是跟着
数据模型走。

取值可以挂在很多对象上（数据类型、`RECORD`、`SERVICE`、`DIAGINST`、`DATAOBJ`、
`ECU`、`VAR`）。本解析器只处理**定义 + ECU/VAR 层的取值**——那是承载 CAN 标识符和
UDS 时序的一层；数据类型和 DTC 上的属性由它们各自的解析器一并报出。

### 6.2 接口名必须从文档里读

**接口名是每份文档自定义的**，通信参数的限定名是 `<接口 qual>.<参数 qual>`。
实测 `COM.INTERFACES` 分类列了 7 个接口：

| 接口 qual | ECU 支持 | 参数数 |
|---|---|---|
| **`CAN`** | ✓ | 40 |
| `CAN_Extended_Addressing` | | 37 |
| `FlexRay_ISO` | | 32 |
| `FlexRay_Autosar2x` | | 34 |
| `DoIP_ISO13400` | | 21 |
| `CAN_FD` | | 42 |
| `CAN_FD_Extended_Addressing` | | 47 |

> 注意 `CAN_Extended_Addressing.P2Client` 这种限定名**不以 `CAN.` 开头**（是 `CAN_`）。
> 按 `"CAN."` 前缀匹配会把这类接口的时序和地址全部漏掉。正确做法是从
> `COM.INTERFACES` 分类读出接口清单，再按 `.` 前缀归属参数。

### 6.3 取值优先级

`定义默认值` → `ECU 上的取值` → `VAR 上的取值`，后者覆盖前者。`source` 标明当前值
来自哪一层（`default`/`ecu`/`variant`），`variants` 给出每个 variant 的最终值。

**实测 353 条属性里 ECU 层只覆盖了 11 条，其余 342 条取定义默认值**——只读 ECU 上的
`UNS`/`ENUM`/`CSTR` 会漏掉几乎全部参数，必须回落到定义的默认值。

`valueText` 做显示层渲染：枚举取 `ETAG` 文本（见
[cdd-format.md §7](cdd-format.md#7-枚举必须读标签文本不能读数值)）；`df='hex'` 的补零
成偶数位（`1792` → `0x0700`、`0` → `0x00`）；其余原样。`display` 是显示格式
（Hexadecimal / Decimal / Binary；枚举没有 `df`，取 `@sort` → `Sort by ID`）。

### 6.4 三个接口入口的区别

- `parse_interfaces()` —— 全部接口，各带 `enabled`（该接口 `@v == 1`）。
- `parse_supported_interfaces()` —— 只要 `enabled` 的。
- `active_interface()` —— 上者的第一个。

**判断这个 ECU 用什么总线、什么时序时必须走后两者**：模板常会提供 CAN FD、DoIP 等
这个 ECU 并未选用的接口，直接拿全量里的某个会得出它并不具备的能力。实测这份文档提供 7 个接口，但该 ECU **只支持 `CAN`**。

### 字段

| 解析目标 | CDD 字段 |
|---|---|
| category / categoryQual | `*DEF@attrcatref` → `ATTRCAT` 的 `NAME/TUV` / `QUAL` |
| kind | 定义标签：`UNSDEF`→unsigned、`SGNDEF`→signed、`ENUMDEF`→enum、`CSTRDEF`→commonString、`STRDEF`→string |
| display / displayFormat | `*DEF@df`（`hex`/`dec`/`bin`）；枚举取 `@sort` |
| default | `*DEF@v`；字符串类取子元素 `COMMONSTRING`/`STRING`/`DEFAULT` 的文本 |
| choices | `ENUMDEF` 下 `ETAG@v` → `TUV` |
| interface / parameter | `QUAL` 按第一个 `.` 拆分，且前缀命中 `COM.INTERFACES` 里的接口才算 |
| value / source | 定义默认值，被 `ECU` 上 `@attrref` 匹配的取值覆盖 |
| variants | 每个 `VAR` 再覆盖一次 |

### 输出

```
AttributeEntry { id, name, qual, description, category, categoryQual, kind,
                 display, displayFormat, default, defaultText, choices,
                 interface, parameter,      # 非接口参数时 interface 为 None
                 value, valueText, source,
                 variants: {varQual: {value, source}} }

Interface { name, qual, enabled, parameters: [AttributeEntry, ...] }
```

实测活动接口 `CAN` 的几个参数：

| 参数 | Display | Default Value | Overwritten Value |
|---|---|---|---|
| `ReqCanId` | Hexadecimal | `0x0700` | **`0x07AA`** |
| `ResCanId` | Hexadecimal | `0x0600` | **`0x07AB`** |
| `ReqCanIdFunc` | Hexadecimal | `0x0750` | **`0x07DF`** |
| `CANFrameFillerByte` | Hexadecimal | `0x00` | **`0xCC`** |
| `RC78Handling` | Sort by ID | `EnabledUnlimited` | **`Enabled`** |
| `P2Client` | Decimal | `150` | |
| `Baudrate` | Decimal | `500000` | |
| `AddrScheme` | Sort by ID | `Normal` | |

两处值得注意：

- `RC78Handling` 是**枚举**被覆盖。覆盖值在 XML 里是个裸数字，标签文本仍要回定义的
  `ETAG` 去查——`valueText` 的枚举解析对默认值和覆盖值同样适用。
- 有几条（`Periodic_Rate_*`、`UudtResCanId`）覆盖值与默认值**相同**，它们的 `source`
  仍是 `"ecu"` 而非 `"default"`——**「有没有被覆盖」和「值是否相同」是两件事**，
  它们确实是被显式写进文件的。

---

## 7. States

解析 `ECUDOC/STATEGROUPS`，给出会话与安全访问状态组。

实测两个组：`Session`（3 个状态）、`SecurityAccess`（2 个）。

状态组的种类要读元素的 `spec` 而不是显示名——显示名是每份文档自定义的。
