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
interface = CddAttributesParser(shared).active_interface(ecu_doc)
tester = CddTester(shared)

tester.detect_bus_kind(interface)      # "can" / "eth"
tester.build_uds_timing(interface)     # {"pTime":150,"pExtTime":2000,"s3Time":4000,...}
tester.build_can_addresses(interface)  # [{"type":"can","canAddr":{...}}, ...]
tester.build(ecu_doc)                  # 整个结构
```

注意传进去的是 `active_interface()` 而不是随便一个接口——理由见
[parsers.md §6.4](parsers.md#64-三个接口入口的区别)。

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
| `dlc` | `CanFdMaxDlc` 标签（`CANFD64` → 64 等） | 8（经典 CAN） |
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
    didList: [...],       # CddDidParser
    dtcList: [...],       # CddDtcParser
    allServiceList: { "0x22": [ {id, name, serviceId, identifier,
                                 request, positiveResponse, negativeResponse,
                                 telegrams}, ... ] },
    # telegrams[].parameters 已按 §5 展开
} } }
```

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
- DoIP 只做到识别和时序取值，**没有生成对应的地址结构**（样本里 DoIP 接口未启用，
  无法验证）。
