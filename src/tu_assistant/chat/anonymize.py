"""普法文章交付前的身份信息检查（T054 / FR-030）。

职责：
1. 从本会话用户输入中按确定性规则抽取候选身份信息（常见单姓人名、五类单位全称）；
2. 统一维护本轮写作/续改/咨询意图判定；
3. 为受保护实体分配类别内稳定、无冲突的虚构代称，一次扫描替换普通正文；
4. 保护经出处校验核准的条款标记与 KB 原文，命中核准区间时整轮暂缓交稿；
5. 为 Reply.citations 构造安全的元数据拷贝，避免原始引文或元数据泄露受保护名称。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..citation.models import Citation

EntityKind = Literal["person", "org"]

CITATION_CONFLICT_NOTICE = (
    "核准的条款出处或原文与本会话中需保护的称呼重合。"
    "为保留准确引文，本轮稿件暂缓交付。"
    "请用 /new 新建会话，以虚构称呼重新描述案情，或请项目方线下核对。"
)

_PERSON_SHORT_POOL = (
    "甲某", "乙某", "丙某", "丁某", "戊某",
    "己某", "庚某", "辛某", "壬某", "癸某",
)
_ORG_SHORT_POOL = (
    "甲单位", "乙单位", "丙单位", "丁单位", "戊单位",
    "己单位", "庚单位", "辛单位", "壬单位", "癸单位",
)

# 中国常见单姓（覆盖常用单姓；复姓不在本期规则范围内）
_COMMON_SURNAMES = frozenset(
    "王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹"
    "彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金"
    "石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵"
    "万钱严覃武戴莫孔向汤常康伍齐倪易乔庞樊兰殷施洪翟安颜牛温芦季"
    "俞章鲁葛申尤毕聂丛焦柳邢路岳梅庄辛管祝左涂谷祁时舒耿牟卜詹关"
    "苗凌费纪靳童曲成游阳裴席卫查屈鲍霍翁隋植甘景薄单包司柏宁柯阮"
    "桂闵欧解强柴华车冉房边辜吉饶刁瞿戚丘古米池滕晋苑邬臧畅宫来苟"
    "全褚廉简娄盖符奚木穆党燕郎邸冀谈姬屠连郜晏"
)

# 名字中不应出现的功能字、标点或虚构称谓字
_NAME_FORBIDDEN_CHARS = frozenset(
    "某的了着过在是有不没很太都也就才还又再把被让给向往从到对于与和跟"
    "或而且但却若如虽因所以为之其此彼这那哪什么怎吗呢吧啊呀哦嗯"
    "说称问想钱法律条款项期内务外上下前后左右里中间个些位名厂院校司企"
)

# 职务语境与自报语境中容易紧随其后的普通词汇（绝非人名）
_NON_PERSON_WORDS = frozenset({
    "任期", "安排", "应当", "应该", "管理", "要钱", "要求", "负责", "代表",
    "组织", "协调", "维护", "保护", "参加", "参与", "主持", "召开", "选举",
    "产生", "连任", "辞职", "兼任", "担任", "出任", "履职", "任职", "卸任",
    "离任", "罢免", "撤换", "协商", "谈判", "签约", "签字", "同意", "批准",
    "审核", "审查", "监督", "检查", "调查", "处理", "解决", "答复", "回复",
    "反映", "汇报", "报告", "提出", "提交", "申请", "投诉", "举报", "起诉",
    "仲裁", "调解", "维权", "帮扶", "慰问", "发放", "支付", "扣除", "拖欠",
    "克扣", "加班", "休假", "请假", "辞退", "开除", "解雇", "解除", "终止",
    "续签", "签订", "变更", "履行", "违反", "违法", "违规", "合法", "合规",
    "规定", "法律", "法规", "条例", "办法", "通知", "公告", "决定", "意见",
    "建议", "方案", "计划", "制度", "章程", "合同", "协议", "工资", "薪酬",
    "待遇", "福利", "社保", "医保", "工伤", "失业", "养老", "生育", "补贴",
    "津贴", "奖金", "提成", "绩效", "考勤", "排班", "工时", "休息", "年假",
    "病假", "产假", "婚假", "丧假", "事假", "职工", "员工", "工人", "人员",
    "群众", "大家", "我们", "你们", "他们", "她们", "自己", "本人", "单位",
    "企业", "公司", "工厂", "车间", "部门", "科室", "班组", "岗位", "职务",
    "职责", "权利", "义务", "责任", "利益", "权益", "问题", "情况", "事情",
    "事项", "工作", "任务", "项目", "业务", "生产", "经营", "安全", "卫生",
    "健康", "劳动", "用工", "招聘", "录用", "试用", "转正", "晋升", "调岗",
    "降薪", "停工", "停产", "裁员", "倒闭", "破产", "清算", "赔偿", "补偿",
    "罚款", "处罚", "处分", "警告", "记过", "降级", "撤职", "可以", "能够",
    "必须", "需要", "不得", "不能", "不会", "没有", "不是", "是否", "如何",
    "怎么", "怎样", "什么", "哪些", "多少", "请问", "咨询", "打听",
    "了解", "帮助", "帮忙", "主席", "经理", "主任", "厂长", "书记", "组长",
    "班长", "队长", "科长", "部长", "处长", "老板", "律师", "老师", "医生",
    "师傅", "同志", "先生", "女士", "高管", "股东", "法人", "财务", "人事",
    "质检", "保安", "司机", "厨师", "护工", "保洁", "客服", "销售", "技术",
    "普通", "新入", "在职", "离职", "退休", "实习", "临时", "正式", "外包",
    "常年", "白班", "夜班", "全职", "兼职", "木工", "瓦工", "电工", "焊工",
    "水电", "起草", "修改", "规章",
})

# 人名之后允许紧跟的多字边界词（优先匹配，防止 3 字名第 3 字被单字词截断）
_RE_PERSON_FOLLOW_MULTI = re.compile(
    r"^(?:先生|女士|同志|师傅|经理|主任|主席|厂长|老师|医生|"
    r"准备|打算|希望|要求|提出|收到|发现|认为|觉得|表示|反映|询问|"
    r"咨询|投诉|举报|申请|起诉|离职|入职|工作|上班|干活|"
    r"安排|通知|决定|组织|负责|扣发|拖欠|克扣|拒绝|强迫|辞退|开除|解雇|调岗|降薪)"
)
# 人名之后允许紧跟的单字边界词
_RE_PERSON_FOLLOW_SINGLE = re.compile(
    r"^(?:说|称|问|想|要|在|于|从|到|向|给|被|把|让|对|和|与|跟|因|为|"
    r"的|了|着|过|是|有|未|不|也|都|就|还|又|已|曾|正|将|做|当|任)"
)

# 自报身份与职务触发语境（短职务词加左边界负向后行断言，避免"门店长/汇总监"等跨词误抽）
_RE_PERSON_INTRO = re.compile(
    r"(?:本人名叫|我名叫|本人叫|我叫|名叫|姓名是|姓名为|姓名|本人是|我是|"
    r"工会副主席|工会主席|工会委员|工会干部|车间主任|法定代表人|"
    r"人事经理|人事主管|财务总监|副厂长|厂长|副总经理|总经理|"
    r"副经理|经理|副主任|主任|主管|董事长|副院长|(?<!医)院长|副校长|(?<!高)校长|"
    r"副书记|书记|班组长|组长|班长|队长|科长|(?<!内)部长|(?<!处)处长|(?<!车)站长|(?<!门)店长|"
    r"(?<!汇)总监|包工头|工头|老板|护士长)"
)

# 单位名：法律材料剥离用正则
_RE_FORMAL_MARKER = re.compile(r"〔《[^》]+》[^〕]*〕")
_RE_BOOK_TITLE = re.compile(r"《[^》]+》")
_RE_CLAUSE_QUOTE = re.compile(
    r"第[0-9零〇一二三四五六七八九十百千]+条"
    r"(?:第[0-9零〇一二三四五六七八九十]+款)?"
    r"(?:第[0-9零〇一二三四五六七八九十]+项)?"
    r"(?:规定)?\s*[：:]?\s*(?:“[^”]+”|「[^」]+」|\"[^\"]+\")"
)
_RE_QUOTE_LINE = re.compile(r"^>\s?")

# 单位后缀（长后缀优先）与后缀后固定词素检查
_RE_ORG_SUFFIX = re.compile(
    r"(有限责任公司|股份有限公司|集团有限公司|有限公司|公司|集团|工厂|厂|医院|学校)"
)
# 仅拦截明确的固定词素组合，不误杀"公司法定代表人/公司章程/公司制定/厂办公室/厂内部/厂规章制度"
_RE_COMPANY_MORPHEME_AFTER = re.compile(r"^(?:法(?!定|律|院|官)|债券)")
_RE_FACTORY_MORPHEME_AFTER = re.compile(r"^(?:房|区|长)")
_RE_GROUP_MORPHEME_AFTER = re.compile(r"^(?:军|化|体)")

# 单位左侧切分的多字引导词（按长度降序）
_ORG_LEFT_PHRASES = sorted(
    (
        "我们是在", "目前在", "现在在", "原来在", "之前在", "一直在",
        "本人是", "本人叫", "我是在", "我们是", "我们在", "他是在", "她是在",
        "就职于", "供职于", "受雇于", "任职于", "工作于", "隶属于",
        "我是", "我在", "你是", "你在", "他是", "他在", "她是", "她在",
        "咱们", "我们", "你们", "他们", "她们", "自己", "本人",
        "入职", "离开", "来自", "属于", "关于", "针对", "起诉", "投诉",
        "举报", "代表", "作为", "因为", "由于", "如果", "假如", "但是",
        "不过", "而且", "以及", "还有", "或者", "还是", "名为", "名叫",
        "叫做", "称为", "问问", "请问", "听说", "据说", "最近", "目前",
        "现在", "以前", "原来", "去年", "今年", "之前", "之后", "昨天",
        "今天", "一家", "一个", "一所", "一座", "这家", "那家", "该家",
        "本家", "有个", "有家", "曾在", "来到", "进到", "去了", "到了",
        "找到", "告了", "想问", "问下", "帮我", "给我",
        "变更为", "改成", "变成", "转为", "成为", "成立", "设立", "组建",
        "创办", "注册", "注销", "收购", "合并", "分立", "解散", "符合",
        "建立", "开设", "开办", "承包", "挂靠", "构成", "改为", "改制为",
    ),
    key=len,
    reverse=True,
)
# 强定位自报引导词：命中后左边界已精确定位，不再用单字虚词向专名内部切分
_ORG_EXACT_ANCHORS = frozenset({
    "我们是在", "目前在", "现在在", "原来在", "之前在", "一直在",
    "本人是", "本人叫", "我是在", "我们是", "我们在", "他是在", "她是在",
    "就职于", "供职于", "受雇于", "任职于", "工作于", "隶属于",
    "我是", "我在", "你是", "你在", "他是", "他在", "她是", "她在",
    "入职", "离开", "来自", "名为", "名叫", "叫做", "称为",
    "一家", "一个", "一所", "一座", "这家", "那家", "该家", "本家",
    "曾在", "来到", "进到",
})
# 单位左侧切分的强语法单字虚词（移除高频字号用字如 为/和/进/来/正/全/能/得/可/如，保留"某"）
_ORG_LEFT_SINGLE = frozenset(
    "是在于从到由被把给向对跟与让叫的了着过"
    "不没都也就才还又再我你他她它咱这那该"
    "但却若或虽因并仍只已曾说等问讲看找帮替"
)

# 单位泛称成分表：若去掉后缀后的 stem 能完全由这些词组成，视为泛称而非专名
_ORG_GENERIC_TOKENS = sorted(
    {
        "有限责任", "股份有限", "有限", "股份", "外国", "外资", "合资", "独资",
        "国有", "国营", "集体", "私营", "民营", "上市", "非上市", "关联",
        "控股", "参股", "一人", "两合", "无限", "跨国", "小微", "中小",
        "大型", "中型", "小型", "微型", "新设", "存续", "其他", "别的",
        "不同", "所有", "任何", "一般", "普通", "正规", "本地", "外地",
        "公立", "私立", "民办", "公办", "综合", "专科", "三甲", "二甲",
        "社区", "乡镇", "定点", "指定", "合作", "附属", "直属", "职业",
        "技工", "技术", "中等", "高等", "全日制", "寄宿制", "初级", "高级",
        "重点", "实验", "示范", "工业", "农业", "商业", "服务", "制造",
        "加工", "生产", "代工", "老牌", "涉事", "用人", "用工", "派遣",
        "劳务派遣", "劳务", "外包", "承建", "发包", "分包", "总包", "施工",
        "建设", "开发", "物业", "中介", "代理", "销售", "贸易", "商贸",
        "电商", "科技", "网络", "信息", "软件", "互联网", "文化", "传媒",
        "广告", "咨询", "管理", "投资", "金融", "保险", "证券", "银行",
        "地产", "房地产", "建筑", "工程", "装饰", "装修", "物流", "快递",
        "运输", "货运", "客运", "交通", "汽车", "机械", "电子", "电器",
        "化工", "医药", "制药", "医疗", "生物", "食品", "餐饮", "酒店",
        "旅游", "服装", "纺织", "制衣", "制鞋", "玩具", "家具", "印刷",
        "包装", "塑料", "五金", "钢铁", "煤炭", "矿业", "能源", "电力",
        "水利", "环保", "养殖", "种植", "保安", "保洁", "家政", "教育",
        "培训", "养老", "体育", "娱乐", "影视", "出版", "水泥", "造纸",
        "玻璃", "陶瓷", "橡胶", "化纤", "冶金", "炼油", "发电", "供水",
        "供热", "燃气", "电信", "通信", "航空", "航运", "铁路", "港口",
        "仓储", "零售", "批发", "超市", "商场", "百货", "药店", "诊所",
        "美容", "美发", "健身", "维修", "检测", "检验", "认证", "评估",
        "审计", "会计", "律师", "设计", "研发", "印染", "酿酒", "卷烟",
        "烟草", "砖瓦", "木材", "造船", "修船", "机修", "汽修", "模具",
        "注塑", "冲压", "焊接", "电镀", "喷涂", "装配", "组装", "精密",
        "自动化", "新能源", "光伏", "电池", "芯片", "半导体", "日化",
        "化妆品", "保健品", "农产品", "水产", "畜牧", "林业", "渔业",
        "采矿", "冶炼", "石油", "天然气", "化肥", "农药", "涂料", "建材",
        "钢材", "矿山", "园林", "绿化", "市政", "路桥", "消防", "安防",
        "数据", "硬件", "游戏", "动漫", "直播", "跨境", "供应链", "冷链",
        "生鲜", "外卖", "租赁", "融资", "担保", "拍卖", "信托", "基金",
        "期货", "资产", "财富", "财务", "税务", "人力", "人力资源", "猎头",
        "环卫", "搬家", "测绘", "勘察", "监理", "造价", "招标", "旅行",
        "宾馆", "民宿", "饭店", "酒楼", "快餐", "团餐", "食堂", "饮料",
        "酒业", "乳业", "肉类", "粮油", "零食", "果蔬", "器械", "耗材",
        "中药", "西药", "兽药", "饲料", "宠物", "口腔", "眼科", "妇产",
        "儿科", "骨科", "肿瘤", "康复", "体检", "精神", "传染病", "人民",
        "中心", "第一", "第二", "第三", "第四", "第五", "第六", "第七",
        "第八", "第九", "第十", "中学", "小学", "大学", "学院", "高中",
        "初中", "职高", "中专", "大专", "技校", "体校", "艺校", "党校",
        "军校", "警校", "驾校", "夜校", "成人", "特殊", "国际", "双语",
        "外国语", "师范", "财经", "政法", "理工", "农林", "医科", "艺术",
        "音乐", "美术", "舞蹈", "戏剧", "电影", "航海", "铁道", "邮电",
        "地质", "轻工", "烹饪", "护理", "企业", "单位", "分支", "母", "子",
        "分", "总", "大", "小", "老", "新", "黑", "原", "现", "前", "后",
        "本", "该", "同", "各", "某", "一", "两", "三", "多", "中", "西",
        "省", "市", "区", "县", "镇", "乡", "村",
    },
    key=len,
    reverse=True,
)
_RE_FICTIONAL_ORG = re.compile(
    r"^[甲乙丙丁戊己庚辛壬癸](?:单位|公司|厂|工厂|集团|医院|学校)$"
)
_RE_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")

# 意图判定正则
_RE_NEGATE_ARTICLE = re.compile(
    r"(?:不要|别|不用|不必|先不|暂不|不打算|不想|不让|不准|禁止|阻止|不允许)"
    r"(?:写|撰写|生成|发|出|改|整理)(?:普法|以案说法)?(?:文章|短文|稿件|稿子|稿|案例|宣传)"
)
_RE_EXPLICIT_WRITE = re.compile(
    r"(?:(?<!不让)(?<!不准)(?<!禁止)(?<!阻止)(?<!不要)(?<!不想)(?<!不能)(?<!不用)(?<!不必)(?<!别)"
    r"(?:写|撰写|生成|出|来|给我|帮我写|帮我生成|帮忙写|起草)"
    r"[^。！？\n]{0,36}?"
    r"(?:普法(?:宣传)?(?:文章|短文|案例)|以案说法(?:的)?(?:文章|短文)?|"
    r"宣传栏(?:短文|文章|稿)|科普(?:文章|短文)|一?篇(?:文章|短文|普法文)|几篇(?:文章|短文|普法文)|"
    r"[两二三四五六七八九十\d]+篇(?:文章|短文|普法文|以案说法)))"
    r"|(?:(?:把|将)[^。！？\n]{0,30}?(?:整理成|改写成|写成|编成)[^。！？\n]{0,16}?"
    r"(?:文章|短文|普法案例|普法文章|以案说法|宣传稿))"
)
_RE_EXPLICIT_REVISE = re.compile(
    r"(?:(?:把|将)?(?:文章|这篇|上一篇|稿子|稿件|初稿|以案说法|普法提示|案例部分)"
    r"[^。！？\n]{0,24}?(?:改|修改|调整|换成|换一个|换个|重写|润色|简化|通俗|再发一版|再来一版))"
)
_RE_ELLIPTICAL_REVISE = re.compile(
    r"(?:再通俗|更通俗|通俗一点|通俗些|口语化|换个违法主体|换一个违法主体|"
    r"换个主体|换一个主体|换个背景|换个行业|换个场景|再发一版|重发一版|"
    r"改一版|改一下|再改|重写|缩短|精简|扩写|语气再|语言再|"
    r"上面(?:那篇|这篇|写的|生成的)[^。！？\n]{0,12}?(?:改|修改|换成|重写|通俗))"
)
_RE_EXPLICIT_CONSULT = re.compile(
    r"(?:只问|只想问|单纯咨询|条款适用吗|适用吗|合法吗|违法吗|构成违法吗|"
    r"怎么处理|怎么维权|怎么办|有什么法律责任|承担什么责任|是不是必须)"
)
# 回复结构判定：标准小节或加粗小节，且需 ≥2 个小节（单个"案例"不足以认定出稿）
_RE_REPLY_ARTICLE_SECTION = re.compile(
    r"(?m)^(?:#{1,3}\s*|\*\*)(?:案例|以案说法|普法提示)(?:\*\*)?\s*$"
)
_RE_REPLY_H1 = re.compile(r"(?m)^# ")
_RE_REPLY_CONSULT_STRUCTURE = re.compile(r"违法行为认定|适用条款|法律责任")


@dataclass
class EntityRecord:
    name: str
    kind: EntityKind


@dataclass
class AnonymizeState:
    """会话内维护的有序实体与代称状态（仅内存）。"""

    entities: list[EntityRecord] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    article_task_active: bool = False

    def known_names(self) -> set[str]:
        return {e.name for e in self.entities}

    def kind_of(self, name: str) -> EntityKind | None:
        for e in self.entities:
            if e.name == name:
                return e.kind
        return None

    def register(self, name: str, kind: EntityKind) -> bool:
        if any(e.name == name for e in self.entities):
            return False
        self.entities.append(EntityRecord(name=name, kind=kind))
        return True


@dataclass
class AnonymizeResult:
    text: str
    person_replacements: int = 0
    org_replacements: int = 0
    blocked: bool = False


def strip_legal_material(text: str) -> str:
    """划去输入中的正式引用标记、紧随的 > 引文行、书名号及可界定的条款原文。"""
    lines = text.split("\n")
    out_lines: list[str] = []
    in_formal_quote = False
    for line in lines:
        stripped = line.lstrip("\r")
        if in_formal_quote:
            if not stripped.strip():
                out_lines.append("")
                continue
            if _RE_QUOTE_LINE.match(stripped):
                out_lines.append(" ")
                continue
            in_formal_quote = False
        if _RE_FORMAL_MARKER.search(line):
            cleaned = _RE_FORMAL_MARKER.sub(" ", line)
            out_lines.append(cleaned)
            in_formal_quote = True
        else:
            out_lines.append(line)
    res = "\n".join(out_lines)
    res = _RE_BOOK_TITLE.sub(" ", res)
    res = _RE_CLAUSE_QUOTE.sub(" ", res)
    return res


def _is_generic_org_stem(stem: str) -> bool:
    """判断去掉后缀后的单位主体是否完全由泛称成分组成。"""
    if not stem:
        return True
    n = len(stem)
    dp = [False] * (n + 1)
    dp[0] = True
    for i in range(n):
        if not dp[i]:
            continue
        for tok in _ORG_GENERIC_TOKENS:
            end = i + len(tok)
            if end <= n and stem[i:end] == tok:
                dp[end] = True
    return dp[n]


def _trim_org_left(prefix: str) -> str:
    """从单位候选左侧剥离引导短语与虚词，保留专名与可能的'某'前缀。"""
    s = prefix
    # 1. 在前缀内寻找最靠右的强多字引导短语
    best_cut = 0
    best_phrase = ""
    for phrase in _ORG_LEFT_PHRASES:
        idx = s.rfind(phrase)
        if idx >= 0:
            cut = idx + len(phrase)
            if cut > best_cut or (cut == best_cut and len(phrase) > len(best_phrase)):
                best_cut = cut
                best_phrase = phrase
    if best_cut > 0:
        s = s[best_cut:]
    exact_anchor = best_phrase in _ORG_EXACT_ANCHORS
    # 2. 在剩余前缀内寻找强语法单字虚词切分（如 "我在上海的华为技术有限公司" 中的 "的"）
    for i in range(len(s) - 1, -1, -1):
        if s[i] in _ORG_LEFT_SINGLE:
            s = s[i + 1 :]
            break
    # 3. 处理并列连词"和"（如"A公司和B厂""分支机构和分公司"）：
    #    位于开头（he_idx == 0）始终切分；内部（he_idx >= 2）仅在未命中强锚点时切分
    he_idx = s.rfind("和")
    if he_idx == 0 or (he_idx >= 2 and not exact_anchor):
        s = s[he_idx + 1 :]
    # 4. 未命中强锚点时剥离前缀最开头的动词单字（如"去参股公司"），保护"我在来伊份食品公司"
    if not exact_anchor:
        while s and s[0] in "去来为":
            s = s[1:]
    return s


def _is_org_morpheme_after(suffix: str, tail: str) -> bool:
    """判断后缀紧跟文本是否属于固定词素（如 公司法/公司债券/厂房/厂区/厂长/集团军）。"""
    if not tail:
        return False
    if suffix.endswith("公司"):
        return bool(_RE_COMPANY_MORPHEME_AFTER.match(tail))
    if suffix in {"厂", "工厂"}:
        return bool(_RE_FACTORY_MORPHEME_AFTER.match(tail))
    if suffix == "集团":
        return bool(_RE_GROUP_MORPHEME_AFTER.match(tail))
    return False


def _extract_orgs(cleaned: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for run in _RE_CJK_RUN.finditer(cleaned):
        seg = run.group(0)
        seg_offset = run.start()
        pos = 0
        while pos < len(seg):
            m = _RE_ORG_SUFFIX.search(seg, pos)
            if m is None:
                break
            suffix = m.group(1)
            end = m.end()
            raw_prefix = seg[pos:m.start()]
            trimmed = _trim_org_left(raw_prefix)
            candidate = trimmed + suffix
            pos = end
            # 右侧固定词素检查：排除 "公司法/公司债券/厂房/厂区/厂长/集团军"，不误杀带专名的业务语境
            if _is_org_morpheme_after(suffix, seg[end:]):
                continue
            if not trimmed:
                continue
            if candidate.startswith("某") or _RE_FICTIONAL_ORG.match(candidate):
                continue
            if _is_generic_org_stem(trimmed):
                continue
            cand_start = seg_offset + m.start() - len(trimmed)
            found.append((cand_start, candidate))
    return found


def _is_valid_person_name(cand: str) -> bool:
    if len(cand) not in (2, 3):
        return False
    if cand[0] not in _COMMON_SURNAMES:
        return False
    if any(ch in _NAME_FORBIDDEN_CHARS for ch in cand[1:]):
        return False
    if cand in _NON_PERSON_WORDS:
        return False
    return not (
        len(cand) == 3
        and (cand[1:] in _NON_PERSON_WORDS or cand[:2] in _NON_PERSON_WORDS)
    )


def _extract_persons(cleaned: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for m in _RE_PERSON_INTRO.finditer(cleaned):
        after_pos = m.end()
        # 允许引导词后有可选空白或冒号（如 "姓名：陈实"）
        tail_slice = cleaned[after_pos:]
        ws_match = re.match(r"^[：:\s]*", tail_slice)
        shift = ws_match.end() if ws_match else 0
        start_pos = after_pos + shift
        cjk_match = _RE_CJK_RUN.match(cleaned, start_pos)
        if not cjk_match:
            continue
        run = cjk_match.group(0)
        cand: str | None = None
        if len(run) == 2:
            if _is_valid_person_name(run):
                cand = run
        elif len(run) == 3:
            if _is_valid_person_name(run):
                cand = run
            elif (
                _RE_PERSON_FOLLOW_SINGLE.match(run[2:])
                and _is_valid_person_name(run[:2])
            ):
                cand = run[:2]
        elif len(run) > 3:
            # 先按多字明确后接词匹配（3 字名优先于 2 字名，避免 3 字名第 3 字被单字虚词截断）
            for length in (3, 2):
                head = run[:length]
                rest = run[length:]
                if _RE_PERSON_FOLLOW_MULTI.match(rest) and _is_valid_person_name(head):
                    cand = head
                    break
            if cand is None:
                for length in (2, 3):
                    head = run[:length]
                    rest = run[length:]
                    if _RE_PERSON_FOLLOW_SINGLE.match(rest) and _is_valid_person_name(head):
                        cand = head
                        break
        if cand is not None:
            found.append((start_pos, cand))
    return found


def _detect_reclaimed_aliases(cleaned: str, state: AnonymizeState) -> list[tuple[int, str, EntityKind]]:
    """检查用户是否在明确自报身份语境中占用了已分配的虚构代称。"""
    hits: list[tuple[int, str, EntityKind]] = []
    alias_to_kind: dict[str, EntityKind] = {}
    for orig, alias in state.aliases.items():
        kind = state.kind_of(orig)
        if kind is not None:
            alias_to_kind[alias] = kind
    for alias, kind in alias_to_kind.items():
        pat = re.compile(
            r"(?:本人名叫|我名叫|本人叫|我叫|名叫|姓名(?:是|为)?|本人是|我是|"
            r"我在|就职于|供职于|受雇于|任职于|单位(?:是|为)?|公司(?:是|为)?)"
            r"[：:\s]*"
            + re.escape(alias)
            + r"(?=$|[^\u4e00-\u9fff]|的|在|是|说|问|有|被|把|向|给|从|到|"
            r"和|与|跟|也|都|就|还|做|上班|工作|里)"
        )
        m = pat.search(cleaned)
        if m is not None:
            hits.append((m.start(), alias, kind))
    return hits


def extract_user_entities(
    user_message: str,
    state: AnonymizeState,
    user_entities_compat: set[str] | None = None,
) -> list[EntityRecord]:
    """从单条用户消息抽取候选并按出现次序更新会话状态，返回本轮新增记录。"""
    cleaned = strip_legal_material(user_message)
    candidates: list[tuple[int, str, EntityKind]] = []

    for pos, name in _extract_orgs(cleaned):
        candidates.append((pos, name, "org"))
    for pos, name in _extract_persons(cleaned):
        candidates.append((pos, name, "person"))

    # 对已分配代称单查明确自报身份语境
    reclaimed = _detect_reclaimed_aliases(cleaned, state)
    reclaimed_aliases = {alias for _, alias, _ in reclaimed}
    if reclaimed_aliases:
        # 解除原实体对被占用代称的映射，待当轮起重新分配
        for orig in [k for k, v in state.aliases.items() if v in reclaimed_aliases]:
            del state.aliases[orig]
        candidates.extend(reclaimed)

    candidates.sort(key=lambda item: item[0])
    added: list[EntityRecord] = []
    for _, name, kind in candidates:
        if state.register(name, kind):
            added.append(EntityRecord(name=name, kind=kind))
        if user_entities_compat is not None:
            user_entities_compat.add(name)
    return added


def classify_turn_intent(
    user_message: str,
    reply_text: str,
    *,
    has_citation: bool,
    article_task_active: bool,
    current_intent: str | None,
) -> tuple[str | None, bool, bool]:
    """判定本轮会话意图、文章任务续改状态及是否需执行文章身份检查。

    返回 (new_intent, new_article_task_active, should_check_identity)。
    """
    negated = bool(_RE_NEGATE_ARTICLE.search(user_message))
    explicit_write = (not negated) and bool(_RE_EXPLICIT_WRITE.search(user_message))
    explicit_revise = (not negated) and bool(_RE_EXPLICIT_REVISE.search(user_message))
    elliptical_revise = (
        (not negated)
        and article_task_active
        and bool(_RE_ELLIPTICAL_REVISE.search(user_message))
    )
    explicit_consult = negated or (
        not explicit_write
        and not explicit_revise
        and not elliptical_revise
        and bool(_RE_EXPLICIT_CONSULT.search(user_message))
    )

    if explicit_write or explicit_revise or elliptical_revise:
        return "article", True, True

    if explicit_consult:
        return "consult", False, False

    # 无明确请求时，结合实际文章小节及上下文判断（单个"案例"不足以认定出稿）
    section_count = len(_RE_REPLY_ARTICLE_SECTION.findall(reply_text))
    has_h1 = bool(_RE_REPLY_H1.search(reply_text))
    reply_is_article = section_count >= 2 or (has_h1 and section_count >= 1)
    if reply_is_article:
        return "article", True, True

    if _RE_REPLY_CONSULT_STRUCTURE.search(reply_text) or has_citation:
        return "consult", False, False

    # 模糊开场或追问：保持当前对话状态，不触发文章检查
    return current_intent, article_task_active, False


def _iter_alias_candidates(kind: EntityKind):
    short_pool = _PERSON_SHORT_POOL if kind == "person" else _ORG_SHORT_POOL
    yield from short_pool
    prefix = "人员" if kind == "person" else "单位"
    idx = 1
    while True:
        yield f"{prefix}{idx}"
        idx += 1


def _alias_conflicts(
    cand: str,
    draft_text: str,
    known_names: set[str],
    used_aliases: set[str],
) -> bool:
    if cand in used_aliases or cand in draft_text:
        return True
    return any(cand == name or name in cand or cand in name for name in known_names)


def _ensure_alias(
    name: str,
    state: AnonymizeState,
    draft_text: str,
) -> str:
    if name in state.aliases:
        return state.aliases[name]
    kind = state.kind_of(name) or "person"
    known = state.known_names()
    used = set(state.aliases.values())
    for cand in _iter_alias_candidates(kind):
        if not _alias_conflicts(cand, draft_text, known, used):
            state.aliases[name] = cand
            return cand
    raise RuntimeError("unreachable")


def _spans_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and a1 > b0


def anonymize_article_text(
    text: str,
    state: AnonymizeState,
    protected_spans: list[tuple[int, int]] | None = None,
) -> AnonymizeResult:
    """对文章交付文本执行身份检查与替换。

    - 按长度优先、一次扫描命中所有受保护全称；
    - 任一命中与核准法条区间 protected_spans 相交时，整轮暂缓交稿；
    - 否则按实体初次出现顺序分配稳定代称并一次性替换。
    """
    if not state.entities:
        return AnonymizeResult(text=text)

    ordered_names = [e.name for e in state.entities]
    pattern = re.compile(
        "|".join(re.escape(n) for n in sorted(ordered_names, key=len, reverse=True))
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return AnonymizeResult(text=text)

    spans = protected_spans or []
    for m in matches:
        s, e = m.start(), m.end()
        if any(_spans_overlap(s, e, ps, pe) for ps, pe in spans):
            return AnonymizeResult(text=CITATION_CONFLICT_NOTICE, blocked=True)

    # 按实体初次出现顺序为本轮命中的未分配实体分配代称
    hit_names = {m.group(0) for m in matches}
    for name in ordered_names:
        if name in hit_names:
            _ensure_alias(name, state, text)

    chunks: list[str] = []
    cursor = 0
    person_count = 0
    org_count = 0
    for m in matches:
        s, e = m.start(), m.end()
        orig = m.group(0)
        alias = state.aliases[orig]
        chunks.append(text[cursor:s])
        chunks.append(alias)
        cursor = e
        if state.kind_of(orig) == "org":
            org_count += 1
        else:
            person_count += 1
    chunks.append(text[cursor:])

    return AnonymizeResult(
        text="".join(chunks),
        person_replacements=person_count,
        org_replacements=org_count,
        blocked=False,
    )


def _replace_known_names_plain(
    text: str, state: AnonymizeState, *, draft_text: str = ""
) -> str:
    if not text or not state.entities:
        return text
    ordered_names = [e.name for e in state.entities]
    pattern = re.compile(
        "|".join(re.escape(n) for n in sorted(ordered_names, key=len, reverse=True))
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return text
    hit_names = {m.group(0) for m in matches}
    conflict_scope = f"{draft_text}\n{text}" if draft_text else text
    for name in ordered_names:
        if name in hit_names:
            _ensure_alias(name, state, conflict_scope)
    chunks: list[str] = []
    cursor = 0
    for m in matches:
        chunks.append(text[cursor : m.start()])
        chunks.append(state.aliases[m.group(0)])
        cursor = m.end()
    chunks.append(text[cursor:])
    return "".join(chunks)


def sanitize_citations(
    citations: list[Citation],
    state: AnonymizeState,
    *,
    draft_text: str = "",
) -> list[Citation]:
    """为文章路径构造安全的 Citation 列表，清洗四种 verdict 的任意文本字段。"""
    if not state.entities:
        return citations
    sanitized: list[Citation] = []
    for c in citations:
        sanitized.append(
            Citation(
                raw=_replace_known_names_plain(c.raw, state, draft_text=draft_text),
                title=_replace_known_names_plain(c.title, state, draft_text=draft_text),
                version_label=_replace_known_names_plain(
                    c.version_label, state, draft_text=draft_text
                ),
                article_no=c.article_no,
                paragraph_no=c.paragraph_no,
                item_no=c.item_no,
                quoted_text=(
                    _replace_known_names_plain(
                        c.quoted_text, state, draft_text=draft_text
                    )
                    if c.quoted_text is not None
                    else None
                ),
                resolved_clause_id=c.resolved_clause_id,
                verdict=c.verdict,
                span=c.span,
                quote_span=c.quote_span,
                fallback_para_match=c.fallback_para_match,
            )
        )
    return sanitized
