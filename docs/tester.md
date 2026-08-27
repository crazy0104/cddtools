# cdd_tester：派生层

把解析结果**重新组织成一个测试仪建立连接所需要的形状**：CAN 标识符、ISO-TP 参数、
UDS 时序，以及按服务 ID 索引的服务表。


## 1. 怎么用

```python
from cddtools import load_ecu_doc, parse_tester_info
from cddtools.cdd_attributes_parser import CddAttributesParser
from cddtools.cdd_tester import CddTester

# 高层：一行拿到全部
result = parse_tester_info("examples/CddTools.cdd")   # {"error":0,"data":{ecu:{variant:{...}}}}

# 或者分步，只要其中一部分
shared, ecu_doc = load_ecu_doc("examples/CddTools.cdd")
tester = CddTester(shared)
interface = tester.supported_interfaces(ecu_doc)[0]

tester.detect_bus_kind(interface)      # "can" / "eth"
tester.build_uds_timing(interface)     # {"pTime":150,"pExtTime":2000,"s3Time":4000,...}
tester.build_can_addresses(interface)  # [{"type":"can","canAddr":{...}}, ...]
tester.build_eth_addresses(interface)  # [{"type":"eth","ethAddr":{...}}, ...]
tester.build(ecu_doc)                  # 整个结构
```

`build()` 输出**每个变体 × 每个受支持接口**一个测试仪，不是只取活动接口。命名规则：

| 变体数 | 接口数 | 键 |
|---|---|---|
| 任意 | 1 | 变体 qual |
| 1 | 多 | 接口 qual |
| 多 | 多 | `变体.接口` |

`supported_interfaces()` 按 `COM.INTERFACES` 属性类别找（见
[parsers.md §6.4](parsers.md#64-三个接口入口的区别)）——通信参数在 CDD 里就是普通属性，
类别是文档自己给的分组。一个都没有时 `build()` 直接报错，而不是返回空结构。

## 2. 总线类型靠参数集判断，不靠名字

接口名是文档自定义的（见 [parsers.md §6.2](parsers.md#62-接口名必须从文档里读)），
`FlexRay_Autosar2x`、`DoIP_ISO13400` 这类名字没法用字符串匹配可靠判断总线。
所以 `detect_bus_kind()` 看的是**这个接口有哪些参数**：

- 有 `ReqCanId` / `ResCanId` / `CanIdType` → `"can"`
- 有 `CP_DoIP*` / `CP_P2Max*` / `CP_P6Max*` 前缀的参数 → `"eth"`

## 3. 参数名映射

CAN 地址和时序的 key 来自活动接口下的通信参数，带回退：

| 输出 | 通信参数 | 缺省 |
|---|---|---|
| `canIdTx` / `SA` | `ReqCanId` | — |
| `canIdRx` / `TA` | `ResCanId` | — |
| Functional `canIdTx` | `ReqCanIdFunc` | 无则不生成 Functional 条目 |
| `addrFormat` | `AddrScheme` / `AddrSchemeFunc` 的**枚举标签**大写 | NORMAL |
| `idType` | `CanIdType` / `CanIdTypeFunc` 的**枚举标签**含 "29" 即 EXTENDED；参数缺失时才退回按 CAN ID 是否 > `0x7FF` 判定 | STANDARD |
| `bs` / `stMin` | `Blocksize` / `StMin` | 0 / 10 |
| `nAs` `nAr` `nBs` `nCr` | `TimeoutAs` `TimeoutAr` `TimeoutBs` `TimeoutCr` | 1000 |
| `nBr` / `nCs` | `TimeBr` / `TimeCs` | 0 |
| `maxWTF` | `MaxWTF` → `MaxNumberOfWaitFrames` → `Max_number_Wait_Frames` | 0 |
| `paddingValue` / `padding` | `CANFrameFillerByte` / `FillerByteHandling` | 0x0 / true |
| `AE` | `AddressExtension` | 0 |
| `baudrate` | `Baudrate` | 无则不输出 |
| `canfd` | `CanFdHandling` 标签 == `Enabled` | false |
| `brs` | `CanFdBrsHandling` 标签 == `Enabled`（且 canfd 为真） | false |
| `dlc` | `CanFdMaxDlc` 标签（`CANFD64` → 64 等），无标签时按裸 DLC 码（15 → 64） | 8（经典 CAN） |
| `canfd` / `brs` | `CanFdHandling` / `CanFdBrsHandling` 的标签（大小写无关），无标签时按数值 ≠ 0 | false |
| `dataBaudrate` | `CanFdDataBaudrate`，仅 CAN FD 接口 | 无则不输出 |
| `pTime` | `P2Client` → `CP_P2Max_Ecu` → `CP_P2Max` | 无则不输出 |
| `pExtTime` | `P2ExClient` → `CP_P2Star_Ecu` → `CP_P2Star` | 无则不输出 |
| `s3Time` | `S3Client` → `CP_TesterPresentTime` | 无则不输出 |

**为什么要多个候选名**：同一概念在不同文档里叫法不同，等待帧上限就有三种写法；
`StMin` 在一份文档归 Timing 分类、在另一份归 Communication，所以查找只按参数名、
不按分类。

## 4. 服务表 `allServiceList`

按**请求报文的第一个字节**分组——那个字节就是 `CONSTCOMP spec='sid'` 的值，是文档里
写死的实际 SID，不是从类名猜的：

```python
sid = f"0x{request['bytes'].split()[0]}"   # "10 01" -> "0x10"
```

每个服务条目带 `params` / `respParams`——请求和肯定响应里逐个可编辑的参数，顺序就是
报文里的顺序（SID 那个常量不算参数）：

| 报文组件 | 变成什么 |
|---|---|
| `CONSTCOMP spec='sid'` | 跳过 |
| 其他 `CONSTCOMP` | 定值参数，不可编辑 |
| `STATICCOMP` | 定值参数，名字取数据类型名（`spec` 为 `id`/`sub`/`accm` 时不可编辑） |
| 指向电报的 payload 组件 | 展开成该电报的每个参数 |
| `DIDDATAREF` 参数 | 展开成该 DID 的每个成员，成员自己命名（同一 DID 的成员常共用数据类型） |
| `RECORDDATAOBJ` 参数 | 故障记忆条目，即 3 字节 DTC |
| 文档没给内容的 payload | 一个可编辑、可删除的字节 |

`subfunc` 取请求里 `spec` 为 `sub` 或 `accm` 的组件的第一个字节——SecurityAccess 用的
是 `accm`。

## 5. 参数展开：给其他模块用的那一层

解析器只给电报参数的结构 + `dataTypeQual`，要真的收发报文还差一层。
`expand_parameter()` 把数据类型的细节内联到每个参数上：

| 字段 | 来源 | 用途 |
|---|---|---|
| `encoding` | 数据类型 `codedValue.encoding` → 短码（`uns`/`sgn`/`asc`/`dbl`…） | 原始值怎么解释 |
| `byteOrder` | `codedValue.byteOrder` → `big_endian`/`little_endian` | |
| `factor` / `offset` | `linear`，非线性类型取 `1.0` / `0.0` | 原始值 ↔ 物理值换算 |
| `unit` / `precision` | `physicalValue` | 显示 |
| `choices` | 文本表 `textTable` → `{原始值: 文字}` | 枚举参数的取值 |
| `bitGroups` | packet 数据类型的位域成员摊平 | 一个字节里打包多个子值时逐个编解码 |
| `startBit` | 见 §5.1 | CAN 信号工具的起始位约定 |
| `value` | `{"type":"Buffer","data":[...]}` | 可直接上线的字节 |
| `minBitLength` / `maxBitLength` / `variableLength` | 变长字段 | |

`bitGroups` 会**跳过 `GAPDATAOBJ` 保留位但仍推进偏移**。实测服务 `0x28`
（CommunicationControl）的 `CommunicationType` 参数，数据类型 `Communication_Type`
是 1 字节 Packet，展开成三组：

```
(bitOffset 0, bl 1) normalCommunicationMessages              choices {0:off, 1:on}
(bitOffset 1, bl 1) networkManagementCommunicationMessages   choices {0:off, 1:on}
(bitOffset 4, bl 4) communicationTypeNetworks                choices {0:allNetworks, 15:receivingNetworks}
```

中间的 bit 2~3 是保留位，没有出现在 `bitGroups` 里，但第三组的偏移仍然从 4 开始。

### 5.1 `startBit` 是另一套约定

它**不是** `byteNo`/`bitPos` 的替代品，两者都对，只是面向不同消费者：

```
Motorola（大端）: 8*(off//8) + min(7, off%8 + bl - 1)   # 信号起始 = 首字节内的最高位
Intel（小端）:    off                                    # 信号起始 = 偏移本身
```

`offset=0, bl=16, 大端` → `startBit=7`。解析器输出的 `byteNo`/`bitPos` 是文件本身的
字节 / 位偏移，**两套都保留**。

## 6. 输出形状

```
{ ecuQual: { variantQual: {
    id, name,
    type,             # "can" / "eth"
    interface,        # 活动接口的 qual
    udsTime: { pTime, pExtTime, s3Time, testerPresentEnable },
    seqList: [],
    address: [ { type:"can", canAddr:{ name, addrFormat, addrType, SA, TA,
                                       canIdTx, canIdRx, idType,
                                       bs, stMin, nAs, nAr, nBs, nCr, nBr, nCs,
                                       maxWTF, paddingValue, padding,
                                       dlc, brs, canfd, remote, AE } } ],
                # DoIP 接口给的是 { type:"eth", ethAddr:{ name, taType,
                #   virReqType, virReqAddr, entityNotFoundBehavior,
                #   entity:{vin,eid,gid,nodeType,logicalAddr[,nodeAddr]},
                #   tester:{testerLogicalAddr,routeActiveTime,createConnectDelay} } }
    didList: [...],       # CddDidParser
    dtcList: [...],       # CddDtcParser
    allServiceList: { "0x22": [ {id, name, serviceId, subfunc, autoSubfunc,
                                 suppress, desc, params, respParams}, ... ] },
} } }
```

一个参数的形状（`§5` 的展开结果就装在 `meta.cddField` 里）：

```
{ id, name, type,            # "NUM" / "ARRAY" / "ASCII"
  bitLen, value: {type:"Buffer", data:[...]}, phyValue,
  deletable, editable,       # 定值/身份字段为 false
  meta: { type:"CDD-FIELD", cddField:{ ...§5 的字段..., spec } },
  DTC_Table: [...] }         # 仅 DTC 参数
```

`type` 的判定：ASCII/Unicode 编码 → `ASCII`；定长、≤32 位、非二进制、且数据类型不是
`HexDump`/`Memory`/`DataRecord` 这类"字节容器"名 → `NUM`；其余 → `ARRAY`。

## 7. 实测结果

活动接口是 `CAN`：

| 项 | 值 |
|---|---|
| pTime / pExtTime / s3Time | 150 / 2000 / 4000 |
| Physical tx / rx | `0x7aa` / `0x7ab`，STANDARD、NORMAL |
| Functional tx | `0x7df`（三个 CAN ID 都被 ECU 覆盖，默认值分别是 `0x0700`/`0x0600`/`0x0750`） |
| baudrate | 500000 |
| canfd / brs / dlc | false / false / 8 |

文档另外定义了 6 个该 ECU **不支持**的接口，显式去读它们能验证几条分支：

| 接口 | addrFormat | canfd / brs / dlc | detect_bus_kind |
|---|---|---|---|
| `CAN_Extended_Addressing` | **EXTENDED** | false / false / 8 | can |
| `CAN_FD` | NORMAL | **true / true / 64** | can |
| `CAN_FD_Extended_Addressing` | **EXTENDED** | **true / true / 64** | can |
| `DoIP_ISO13400` | — | — | **eth** |

寻址方式和 CAN FD 设置都来自文档而非假设：Normal 与 Extended 两种寻址、经典 CAN 与
CAN FD 两种帧格式在同一份文档里都有样本。

## 8. 已知限制

- `addrFormat` 只做了枚举标签直接大写。Normal 与 Extended 都有样本，**Mixed 缺样本
  验证**。
- `remote` 恒为 `false`：CDD 里没有对应参数，诊断本身也不使用 CAN 远程帧。其余
  `canfd`/`brs`/`dlc` 都是从文档读的（见 §3）。CAN FD 参数只存在于 CAN FD 接口上，
  经典 CAN 接口压根没有 `CanFd*` 参数——所以「没有」本身就等于「经典 CAN」，不是
  「未知」。
- `seqList` 恒为空列表，仅为兼容原有输出结构而保留。
- DoIP 地址结构已经生成（`CP_DoIPLogical*` 四个参数），但样本文档里 DoIP 接口未启用，
  **该分支靠合成文档验证**，没有真实样本。
- `build()` 里的地址只保留测试仪地址本身定义的字段：`baudrate` / `dataBaudrate` 属于
  设备而不是地址，会被去掉。要读它们直接调 `build_can_addresses()`。
