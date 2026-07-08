"""
AI 语义匹配引擎 (v6)
====================
v6 新增: 歧义检测 + 候选列表，支持多轮对话

三层智能架构:
  规则匹配 (0s) → 高置信度(>0.70) 直接返回
               → 中等(0.25-0.70) 多候选 → 标记歧义
               → 低/无(<0.25) → LLM自由推理
"""

import sys
import json
import re
import time
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from src.ai.rkllm_engine import RKLLMEngine


@dataclass
class CandidateItem:
    component_id: int
    component_name: str
    category: str
    voltage: str
    cabinet_id: int
    confidence: float
    stock: int = 0


@dataclass
class MatchResult:
    component_id: Optional[int]
    component_name: str
    cabinet_id: Optional[int]
    confidence: float
    response_text: str
    is_ambiguous: bool = False
    candidates: List[CandidateItem] = field(default_factory=list)


# ═══════════════════════════════════════════════════════
TYPE_KEYWORDS = [
    'wifi', '蓝牙', 'nfc', 'rfid', '射频', '蜂窝', '无线', '通信', 'gprs', '4g', '5g',
    '传感器', '温湿度', '温度', '湿度', '压力', '称重', '红外', '光强度', '光照',
    '土壤', '磁力', '激光', '雷达', '测距', '水质', 'ph', '气体', '霍尔', '电流',
    '电压检测', '加速度', '陀螺仪', 'imu', '毫米波', '心率', '血氧', '指纹',
    'oled', 'lcd', 'tft', '液晶', '显示屏', '触摸屏', 'mipi', 'ips',
    '锂电池', '锂电', '18650', '充电', '降压', '升压', '稳压', 'ldo',
    '供电', '电源', '纽扣电池', '电池', 'buck', 'boost', '充放电',
    '语音', '合成', '识别', '蜂鸣', '录音', '扬声', '麦克风', '拾音',
    '开发板', '单片机', 'mcu', 'arm', 'risc', 'stm32', 'esp32', 'esp8266',
    'rk3588', 'nucleo', '评估板', '核心板', '正点原子', '普中', '野火',
    'arduino', 'k210', 'maix', '树莓派', 'raspberry',
    '摄像头', '扫码', 'hub', 'usb', '串口', 'ttl', 'rs485', 'can', 'spi', 'i2c',
    '杜邦线', '面包板', '散热', '三极管', '二极管', 'led', '电阻', '电容',
    '水泵', '电机', '云台', '发射', '电磁锁', '继电器', '舵机', '步进',
    '支架', '螺丝', '外壳', '散热片',
    'ai', '视觉', 'k210', 'openmv',
]

ALIAS_MAP = {
    '三极管': ['npn', 'pnp', 'mosfet', 'bjt', '2n2222', '2n3904', 'irf'],
    '二极管': ['整流', '1n4007', '1n4148', '肖特基', '稳压管'],
    '单片机': ['stm32', 'esp32', 'arduino', 'mcu', '51单片机', 'avr'],
    '电机': ['马达', '步进', '直流电机', '减速电机', '震动马达'],
    'lcd': ['液晶', '液晶屏', 'tft'],
    'imu': ['陀螺仪', '加速度计', 'mpu6050', 'mpu9250', 'icm'],
}

AMBIGUOUS_KEYWORDS = {
    'led': 'oled',
}

# v6: 歧义判定阈值
SINGLE_MATCH_CONFIDENCE = 0.70   # 超过此置信度且只有1个 → 单匹配
AMBIGUITY_SCORE_GAP = 0.12       # 前两名分数差距小于此值 → 歧义
MIN_CANDIDATE_SCORE = 0.20       # 最低入围分数


class AIEngineImpl:
    """AI 语义匹配引擎 — 规则+LLM 三层架构"""

    def __init__(self):
        self._rkllm: Optional[RKLLMEngine] = None
        self._catalog = ''
        self._components: List[dict] = []
        self._llm_available = False

    def initialize(self, model_path='') -> bool:
        if not model_path:
            model_path = '/opt/smart-locker/models/Qwen2-1.5B_W8A8_RK3588.rkllm'
        self._rkllm = RKLLMEngine(model_path)
        self._llm_available = self._rkllm.init()
        return self._llm_available

    def set_catalog(self, catalog: str):
        self._catalog = catalog
        self._components = []
        for line in catalog.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 4:
                id_name = parts[0].strip()
                id_match = re.match(r'(\d+)\.\s*(.+)', id_name)
                if id_match:
                    self._components.append({
                        'id': int(id_match.group(1)),
                        'name': id_match.group(2).strip(),
                        'category': parts[1].strip(),
                        'voltage': parts[2].strip(),
                        'cabinet': int(re.search(r'\d+', parts[3]).group()) if re.search(r'\d+', parts[3]) else 0
                    })

    # ══════════════════════════════════════════════════
    # 主入口 — v6 歧义检测
    # ══════════════════════════════════════════════════

    def process_query(self, query_text: str) -> MatchResult:
        if not query_text.strip():
            return MatchResult(None, '', None, 0.0, '请说出您需要的器件')

        candidates = self._rule_rank(query_text)

        if not candidates:
            return MatchResult(None, '', None, 0.0,
                f'抱歉，库存中没有匹配"{query_text}"的器件，请换个方式描述')

        best_score, best = candidates[0]
        valid = [(s, c) for s, c in candidates if s >= MIN_CANDIDATE_SCORE]

        if not valid:
            return MatchResult(None, '', None, 0.0,
                f'抱歉，库存中没有匹配"{query_text}"的器件，请换个方式描述')

        # 低分 + 泛匹配 → 拒绝
        if best_score < 0.50 and self._is_generic_match(query_text, best):
            return MatchResult(None, '', None, 0.0,
                f'抱歉，库存中没有匹配"{query_text}"的器件，请换个方式描述')

        # ── v6: 歧义检测 ──
        is_ambig, candidate_items = self._detect_ambiguity(valid)

        if is_ambig:
            # 多个候选，让用户选
            return MatchResult(
                component_id=None,
                component_name='',
                cabinet_id=None,
                confidence=best_score,
                response_text=self._format_candidates(candidate_items),
                is_ambiguous=True,
                candidates=candidate_items
            )

        # 单一匹配 → 直接返回确认
        comp = candidate_items[0]
        resp = (f'{comp.component_name}，{comp.category}，'
                f'{comp.cabinet_id}号柜。确认借出吗？（是/否）')
        return MatchResult(
            component_id=comp.component_id,
            component_name=comp.component_name,
            cabinet_id=comp.cabinet_id,
            confidence=comp.confidence,
            response_text=resp,
            is_ambiguous=False,
            candidates=candidate_items
        )

    def select_candidate(self, index: int) -> Optional[CandidateItem]:
        """用户从候选列表中选择后，根据序号获取对应项"""
        return self._pending_candidates[index] if 0 <= index < len(self._pending_candidates) else None

    # ══════════════════════════════════════════════════
    # v6: 歧义检测
    # ══════════════════════════════════════════════════

    def _detect_ambiguity(self, valid: List[Tuple[float, dict]]) -> Tuple[bool, List[CandidateItem]]:
        """
        判断是否歧义，返回 (is_ambiguous, [CandidateItem, ...])

        歧义条件:
          1. 前两名分数差距 < AMBIGUITY_SCORE_GAP (0.12)
          2. 第一名置信度不够高 (< SINGLE_MATCH_CONFIDENCE)
          3. 有两个及以上 valid candidates
        """
        items = []
        for score, comp in valid:
            items.append(CandidateItem(
                component_id=comp['id'],
                component_name=comp['name'],
                category=comp.get('category', ''),
                voltage=comp.get('voltage', '?'),
                cabinet_id=comp.get('cabinet', 0),
                confidence=min(score, 0.95)
            ))

        # 保存候选列表供 select_candidate 使用
        self._pending_candidates = items

        if len(items) == 1:
            return (False, items)

        # 第一名足够高且与第二名差距大 → 单一匹配
        if items[0].confidence >= SINGLE_MATCH_CONFIDENCE:
            gap = items[0].confidence - items[1].confidence
            if gap > AMBIGUITY_SCORE_GAP:
                return (False, [items[0]])

        # 多个接近 → 歧义，最多返回前8个候选
        return (True, items[:8])

    def _format_candidates(self, items: List[CandidateItem]) -> str:
        """格式化候选列表为可读文本"""
        lines = [f'库存有多款匹配器件，请选择：']
        for i, item in enumerate(items, 1):
            lines.append(f'  {i}. {item.component_name} — {item.category}（{item.cabinet_id}号柜）')
        lines.append('请输入序号（或说"算了"取消）：')
        return '\n'.join(lines)

    # ══════════════════════════════════════════════════
    # 以下与 v5 相同（规则匹配、LLM调用、工具方法）
    # ══════════════════════════════════════════════════

    def _is_generic_match(self, query: str, comp: dict) -> bool:
        query_lower = query.lower()
        name_l = comp['name'].lower()
        q_keywords = self._extract_keywords(query_lower)
        if self._parse_voltage(comp['voltage']) is not None:
            if re.search(r'(\d+\.?\d*)\s*v', query_lower):
                return False
        for kw in q_keywords:
            if kw in name_l:
                return False
        if query_lower in name_l:
            return False
        return True

    def _rule_rank(self, query: str) -> List[tuple]:
        query_lower = query.lower()
        q_voltage = None
        vm = re.search(r'(\d+\.?\d*)\s*v', query_lower)
        if vm:
            q_voltage = float(vm.group(1))
        q_keywords = self._extract_keywords(query_lower)
        chinese_chars = None
        if any('一' <= c <= '鿿' for c in query):
            chinese_chars = [c for c in query_lower if '一' <= c <= '鿿']

        scored = []
        for comp in self._components:
            score = 0.0
            name_l = comp['name'].lower()
            cat_l = comp['category'].lower()
            name_words = set(name_l.replace('-', ' ').replace('/', ' ').split())

            if q_voltage is not None:
                comp_v = self._parse_voltage(comp['voltage'])
                if comp_v is not None:
                    if abs(comp_v - q_voltage) < 0.05:
                        score += 0.35
                    elif abs(comp_v - q_voltage) < 0.5:
                        score += 0.15

            total_matches = 0
            for qw in q_keywords:
                qw_l = qw.lower()
                for nw in name_words:
                    if qw_l in nw:
                        total_matches += 1
                        break
                if total_matches == 0 and qw_l in name_l:
                    total_matches += 1

            if chinese_chars:
                name_chinese = [c for c in name_l if '一' <= c <= '鿿']
                ch_match = sum(1 for c in chinese_chars if c in name_chinese)
                if ch_match >= 3 and ch_match >= len(chinese_chars) * 0.5:
                    total_matches += ch_match // 2

            if total_matches >= 3:
                score += 0.35
            elif total_matches >= 2:
                score += 0.30
            elif total_matches == 1:
                score += 0.20

            for kw in q_keywords:
                if kw in cat_l:
                    score += 0.20
                    break

            query_parts = set(query_lower.replace('-', ' ').replace('/', ' ').split())
            for qp in query_parts:
                if len(qp) >= 3 and qp not in ('模块', '开发板', '传感器', '摄像头', '芯片', '模块'):
                    if qp in name_l or qp.replace(' ', '') in name_l.replace(' ', ''):
                        score += 0.15
                        break
            for qw in q_keywords:
                if len(qw) >= 3 and qw in name_l and qw not in ('模块', '开发板', '传感器'):
                    score += 0.10
                    break

            for amb_q, amb_n in AMBIGUOUS_KEYWORDS.items():
                if amb_q in q_keywords and amb_n in name_l:
                    score -= 0.15

            if score > 0:
                scored.append((score, comp))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    @staticmethod
    def _parse_voltage(voltage_str: str) -> Optional[float]:
        try:
            return float(re.sub(r'[vV]', '', str(voltage_str).strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_keywords(query_lower: str) -> list:
        found = []
        for w in TYPE_KEYWORDS:
            if w in query_lower:
                found.append(w)
        for alias, expansions in ALIAS_MAP.items():
            if alias in query_lower:
                for exp in expansions:
                    found.append(exp)
        return found

    def shutdown(self):
        if self._rkllm:
            self._rkllm.shutdown()
