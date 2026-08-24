"""Deterministic safety and domain guardrails for the Orbit agent.

The LLM is deliberately not the security boundary. These checks run before the
planner, while the system prompt and policy tool provide a second layer for
novel requests. Conversation text is untrusted data and is escaped/redacted
before being embedded in any prompt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_UNTRUSTED_TEXT_CHARS = 100_000


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    category: str
    reason: str
    response: str


_INJECTION_PATTERNS = (
    r"\bignore.{0,50}\b(previous|prior|above|system|developer|instruction|rule)",
    r"\b(disregard|override|bypass).{0,50}\b(instruction|rule|policy|guardrail|system|developer)",
    r"\b(system prompt|developer message|hidden instruction|jailbreak|dan mode|developer mode)\b",
    r"\b(show|print|repeat|reveal|leak).{0,40}\b(system prompt|developer message|hidden instruction|secret)",
    r"\bbo qua.{0,50}\b(chi dan|huong dan|quy tac|prompt|he thong|system|guardrail)",
    r"\b(quen|vo hieu hoa|ghi de|pha bo).{0,50}\b(chi dan|huong dan|quy tac|prompt|he thong)",
    r"\b(hien|in|lap lai|tiet lo|cho xem).{0,40}\b(prompt he thong|system prompt|chi dan an|bi mat)",
    r"\b(gia vo|dong vai).{0,60}\b(khong bi gioi han|khong co quy tac|bo qua quy tac)",
    r"\b(act as|pretend to be|you are now).{0,40}\b(system|developer|unrestricted|dan)\b",
    r"\b(tu gio|bay gio).{0,30}\b(ban la|vai tro cua ban).{0,30}\b(he thong|khong gioi han)",
    r"(?:<|\[)\s*(system|developer)\s*(?:>|\])",
    r"\b(new|updated|replacement) instructions?\s*:",
    r"\b(decode|base64|giai ma).{0,40}\b(follow|execute|lam theo|thuc thi).{0,40}\b(instruction|chi dan)",
    r"\b(base64|rot13|hex encoded|encoded payload)\b",
    r"\b(do anything now|no restrictions?|without restrictions?|unfiltered mode)\b",
    r"\b(chi dan moi|lenh moi|quy tac moi)\s*:",
)

_COMPACT_INJECTION_TERMS = (
    "ignorepreviousinstructions",
    "ignoresysteminstructions",
    "revealsystemprompt",
    "showdevelopermessage",
    "bypassguardrail",
    "boquachidanhethong",
    "tietloprompthethong",
    "vohieuhoaquytac",
)

# These are intentionally intent-shaped patterns, not single forbidden words.
# A work reminder such as "nh\u1eafc t\u00f4i \u0111i kh\u00e1m" must not be blocked merely because
# it mentions health; requests for diagnosis or dangerous instructions are.
_SENSITIVE_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "criminal_activity",
        "l\u1eadp k\u1ebf ho\u1ea1ch, h\u1ed7 tr\u1ee3 ho\u1eb7c t\u1ea1o \u0111i\u1ec1u ki\u1ec7n cho h\u00e0nh vi vi ph\u1ea1m ph\u00e1p lu\u1eadt",
        (
            r"\b(an trom|trom cap|moc tui|cuop|cuop giat|dot nhap|be khoa|pha khoa)\b",
            r"\b(lua dao|gian lan|tong tien|bat coc|buon lau|buon nguoi|rua tien|hoi lo)\b",
            r"\b(hang cam|tien gia|lam gia|gia mao|pha hoai|dot nha|phi tang|danh bac|ca do)\b",
            r"\b(vuot bien|nhap canh trai phep|mai dam|ban dam|mua ban noi tang)\b",
            r"\b(san ban dong vat|chat pha rung|khai thac trai phep|tron lenh trung phat)\b",
            r"\b(pham phap|vi pham phap luat|bat hop phap|hanh vi pham toi)\b",
            r"\b(che giau|xoa|huy|phi tang).{0,35}\b(bang chung|chung cu|dau vet)\b",
            r"\b(tron|ne|vuot).{0,30}\b(canh sat|cong an|truy na|kiem tra an ninh)\b",
            r"\b(steal|theft|burglary|robbery|shoplift|fraud|scam|extortion|kidnap|smuggl)\w*\b",
            r"\b(rob(?:bing|bed)?|mug(?:ging|ged)?|pickpocket)\w*\b",
            r"\b(break into|pick (?:a )?lock).{0,30}\b(house|home|shop|store|office|car|building)\b",
            r"\b(contraband|counterfeit|illegal gambling|tax evasion|trespass)\w*\b",
            r"\b(human trafficking|money laundering|bribery|forge documents?|vandal(?:ism|ize)|arson)\b",
            r"\b(identity theft|organ trafficking|wildlife trafficking|poaching|sanctions evasion)\b",
            r"\b(insider trading|market manipulation|smuggle weapons?)\b",
            r"\b(illegal activity|commit (?:a )?crime|criminal act)\b",
            r"\b(hide|destroy|erase|dispose of).{0,35}\b(evidence|traces?)\b",
            r"\b(evade|escape|avoid).{0,30}\b(police|law enforcement|security check)\b",
        ),
    ),
    (
        "self_harm",
        "t\u1ef1 g\u00e2y h\u1ea1i ho\u1eb7c t\u1ef1 s\u00e1t",
        (
            r"\b(tu tu|tu sat|tu huy hoai|cat tay|self harm|suicide)\b",
            r"\b(cach chet|chet khong dau|ket lieu ban than)\b",
        ),
    ),
    (
        "sexual_content",
        "n\u1ed9i dung t\u00ecnh d\u1ee5c ho\u1eb7c khi\u00eau d\u00e2m",
        (
            r"\b(khieu dam|porn|pornography|nude|anh nong|noi dung 18\+|tinh duc)\b",
            r"\b(sex|sexual).{0,30}\b(explicit|content|story|image|video)\b",
            r"\b(hiep dam|xam hai tinh duc|cuong buc tinh duc|mai dam tre em)\b",
            r"\b(rape|sexual assault|child sexual|sexual exploitation)\b",
        ),
    ),
    (
        "violence_weapons",
        "h\u01b0\u1edbng d\u1eabn b\u1ea1o l\u1ef1c, v\u0169 kh\u00ed ho\u1eb7c ch\u1ea5t n\u1ed5",
        (
            r"\b(cach|huong dan|che tao|lam|mua|su dung).{0,45}\b(bom|sung|vu khi|thuoc no)\b",
            r"\b(giet|sat hai|tan cong|danh|dam|chem|ban).{0,35}\b(nguoi|dong nghiep|nan nhan|muc tieu)\b",
            r"\b(build|make|buy|use).{0,35}\b(bomb|gun|weapon|explosive)\b",
            r"\b(kill|murder|attack|assault|shoot|stab).{0,30}\b(person|coworker|victim|target|someone)\b",
            r"\b(dau doc|bo thuoc doc|am sat|tra tan).{0,30}\b(nguoi|dong nghiep|nan nhan|muc tieu)?\b",
            r"\b(poison|assassinate|torture).{0,30}\b(person|coworker|victim|target|someone)?\b",
        ),
    ),
    (
        "illegal_drugs",
        "h\u01b0\u1edbng d\u1eabn li\u00ean quan \u0111\u1ebfn ma t\u00fay ho\u1eb7c ch\u1ea5t c\u1ea5m",
        (
            r"\b(cach|huong dan|che|nau|mua|ban|su dung|van chuyen).{0,45}\b(ma tuy|meth|cocaine|fentanyl|heroin)\b",
            r"\b(make|cook|buy|sell|transport|smuggle).{0,35}\b(meth|cocaine|fentanyl|heroin|illegal drug)\b",
        ),
    ),
    (
        "cyber_abuse",
        "x\u00e2m nh\u1eadp, \u0111\u00e1nh c\u1eafp d\u1eef li\u1ec7u ho\u1eb7c ph\u00e1 ho\u1ea1i h\u1ec7 th\u1ed1ng",
        (
            r"\b(hack|phishing|malware|ransomware|ddos|keylogger)\b",
            r"\b(danh cap|lay trom|be khoa|vuot qua|bypass).{0,40}\b(mat khau|otp|tai khoan|xac thuc|auth)\b",
            r"\b(sql injection|credential stuffing|reverse shell)\b",
            r"\b(exploit|backdoor|botnet|zero[ -]?day|session hijack|token theft)\b",
            r"\b(pha|xoa|ma hoa|chiem quyen).{0,35}\b(he thong|may chu|du lieu|tai khoan)\b",
        ),
    ),
    (
        "privacy_abuse",
        "thu th\u1eadp ho\u1eb7c ti\u1ebft l\u1ed9 d\u1eef li\u1ec7u c\u00e1 nh\u00e2n nh\u1ea1y c\u1ea3m",
        (
            r"\b(doxx|doxing|theo doi trai phep)\b",
            r"\b(ghi am len|quay len|camera an|nghe len|doc trom tin nhan)\b",
            r"\b(tim|lay|tiet lo|cong khai|danh cap).{0,45}\b(otp|cvv|so the|private key|mat khau|dia chi nha)\b",
            r"\b(stalk|spy on|track secretly|surveil).{0,35}\b(person|coworker|partner|employee|someone)\b",
        ),
    ),
    (
        "harassment_abuse",
        "\u0111e d\u1ecda, qu\u1ea5y r\u1ed1i, c\u01b0\u1ee1ng \u00e9p ho\u1eb7c ng\u01b0\u1ee3c \u0111\u00e3i ng\u01b0\u1eddi kh\u00e1c",
        (
            r"\b(quay roi|bat nat|de doa|tong tien|cuong ep|ep buoc|tra tan|khung bo tinh than)\b",
            r"\b(harass|bully|threaten|blackmail|coerce|torture|intimidate)\w*\b",
            r"\b(revenge porn|nonconsensual intimate|khong co su dong thuan)\b",
        ),
    ),
    (
        "intellectual_property_abuse",
        "x\u00e2m ph\u1ea1m b\u1ea3n quy\u1ec1n ho\u1eb7c v\u01b0\u1ee3t c\u01a1 ch\u1ebf c\u1ea5p ph\u00e9p",
        (
            r"\b(phan mem crack|crack ban quyen|key crack|tai lau|vi pham ban quyen|pha drm)\b",
            r"\b(keygen|pirated (?:software|movie|book)|software crack|crack(?:ing)? (?:a )?license|bypass drm|copyright piracy)\b",
        ),
    ),
    (
        "deception_abuse",
        "l\u1eeba d\u1ed1i, gi\u1ea3 danh, b\u00f4i nh\u1ecd ho\u1eb7c ph\u00e1t t\u00e1n th\u00f4ng tin sai l\u1ec7ch c\u00f3 ch\u1ee7 \u0111\u00edch",
        (
            r"\b(gia danh|mao danh|boi nho|vu khong|phat tan tin gia|tao bang chung gia)\b",
            r"\b(impersonate|defame|fabricate evidence|spread (?:fake news|disinformation))\b",
            r"\b(deepfake).{0,30}\b(tong tien|lua dao|boi nho|blackmail|fraud|defame)\b",
        ),
    ),
    (
        "regulated_advice",
        "t\u01b0 v\u1ea5n chuy\u00ean m\u00f4n y t\u1ebf, ph\u00e1p l\u00fd ho\u1eb7c t\u00e0i ch\u00ednh c\u00f3 r\u1ee7i ro cao",
        (
            r"\b(chan doan|ke don|lieu dung).{0,45}\b(benh|thuoc|dieu tri)\b",
            r"\b(tu van phap ly|lach luat|tron thue|che giau tai san)\b",
            r"\b(cam ket loi nhuan|bao dam loi|all in).{0,35}\b(co phieu|crypto|tien ao|ca cuoc)\b",
        ),
    ),
    (
        "political_persuasion",
        "v\u1eadn \u0111\u1ed9ng ho\u1eb7c thao t\u00fang quan \u0111i\u1ec3m ch\u00ednh tr\u1ecb",
        (
            r"\b(thuyet phuc|van dong|tuyen truyen).{0,45}\b(bau cho|ung vien|dang phai|chinh tri)\b",
            r"\b(persuade|target|campaign).{0,45}\b(voter|candidate|political party)\b",
        ),
    ),
    (
        "hate_extremism",
        "th\u00f9 gh\u00e9t, c\u1ef1c \u0111oan ho\u1eb7c kh\u1ee7ng b\u1ed1",
        (
            r"\b(khung bo|cuc doan|diet chung|thuong dang chung toc)\b",
            r"\b(terroris|genocide|racial supremac|ethnic cleansing)\w*\b",
        ),
    ),
)

# Compact matching catches basic separator/zero-width obfuscation such as
# "\u0103.n t.r.\u1ed9.m", "p h i  t a n g" and "ignore_previous_instructions".
_COMPACT_SENSITIVE_TERMS: dict[str, tuple[str, ...]] = {
    "criminal_activity": (
        "antrom",
        "tromcap",
        "phitangbangchung",
        "luadao",
        "buonlau",
        "ruatien",
        "lamgiagiayto",
        "breakintoahouse",
        "destroytheevidence",
        "moneylaundering",
        "humantrafficking",
    ),
    "self_harm": ("tutu", "tusat", "selfharm", "suicide"),
    "sexual_content": ("khieudam", "noidung18", "pornography"),
    "violence_weapons": ("chetaobom", "chetaovu khi", "buildabomb", "makeaweapon"),
    "illegal_drugs": ("chetaomatuy", "naumeth", "cookmeth", "sellillegaldrugs"),
    "cyber_abuse": ("danhcapmatkhau", "sqlinjection", "credentialsstuffing", "reverseshell"),
    "privacy_abuse": ("tietlootp", "doxxing", "theodoitraiphep"),
    "harassment_abuse": ("quayroi", "batnat", "khungbotinhthan", "revengeporn"),
    "intellectual_property_abuse": ("phanmemcrack", "bypassdrm", "piratedsoftware"),
    "deception_abuse": ("phattantingia", "maodanh", "fabricateevidence", "spreadfakenews"),
}

_WORK_DOMAIN_PATTERNS = (
    r"\b(cong viec|nhiem vu|tasks?|to[ -]?dos?|deadlines?|han chot|uu tien|priorit(?:y|ies))\b",
    r"\b(lich|calendars?|cuoc hop|meetings?|sync|su kien|events?|dat lich|book)\b",
    r"\b(nhac|nhac nho|remind|reminders?|memor(?:y|ies)|schedule)\w*\b",
    r"\b(ghi nho|remember)\b.{0,80}\b(cong viec|du an|task|meeting|cuoc hop|agenda|ticket|build|release)\b",
    r"\b(len ke hoach (?:hom nay|cong viec|du an)|ke hoach (?:cong viec|du an)|work plans?|project plans?)\b",
    r"\b(du an|projects?|nhom|teams?|dong nghiep|khach hang|clients?|workspaces?|standups?)\b",
    r"\b(emails?|bao cao|reports?|tai lieu|documents?|bien ban|agendas?|presentations?)\b",
    r"\b(hoi thoai|conversation|tin nhan|message|chat|tom tat|summar|trich xuat|extract|tim kiem|search)\w*\b",
    r"\b(nang suat|productivity|work profiles?|ho so cong viec)\b",
    r"\b(pham vi|policy|guardrail|quy tac an toan)\b",
    # Engineering/work identifiers are often supplied as terse facts before a follow-up. Requiring
    # the word "project" in "M\u00e3 th\u1eed nghi\u1ec7m l\u00e0 BLUE-42" caused a false out-of-domain refusal and
    # broke working-memory tests even though test/release identifiers are normal work context.
    r"\b(ma (?:thu nghiem|du an|ticket|task|release|build)|test (?:code|id|identifier)|"
    r"ticket|sprints?|releases?|builds?|branches?|repositories?|repos?|staging|production)\b",
)

_SMALL_TALK_PATTERNS = (
    r"^(xin chao|chao|hello|hi|hey)(\b|[!.?, ])",
    r"^(cam on|thanks|thank you)(\b|[!.?, ])",
    r"^(tam biet|bye|goodbye)(\b|[!.?, ])",
    r"\b(ban la ai|ban lam duoc gi|who are you|what can you do)\b",
)

_FOLLOW_UP_PATTERNS = (
    r"\b(khoang thoi gian|time range|date range)\b",
    r"\b(\d+|mot|hai|ba|bay|muoi|may)\s*(phut|gio|ngay|tuan|thang|minutes?|hours?|days?|weeks?|months?)\b",
    r"\b(hom qua|hom truoc|may ngay truoc|tuan truoc|thang truoc|last (?:few )?(?:days?|weeks?|months?))\b",
    r"\b(hom nay|ngay mai|tuan nay|tuan sau|thang nay|thang sau|today|tomorrow|this week|next week)\b",
    r"\b(tu .{1,40} den .{1,40}|from .{1,40} to .{1,40})\b",
    r"^(dung|dung roi|ok|okay|co|khong|yes|no|correct|the first|the second|cai dau|cai thu hai)[!. ]*$",
    r"^(cai do|lich do|task do|cuoc hop do|phuong an do|that one|that event|that task)\b",
)

_CLARIFYING_QUESTION_PATTERNS = (
    r"\?\s*$",
    r"\b(ban muon|ban can|khoang thoi gian nao|ngay nao|luc nao|which|what time|what date|how many)\b",
)

_SECRET_OUTPUT_PATTERNS = (
    r"(?:postgres(?:ql)?|mysql|mariadb|mongodb|redis)(?:\+\w+)?://[^\s]+",
    r"\bsk-[a-z0-9_-]{16,}\b",
    r"\baiza[a-z0-9_-]{20,}\b",
    r"\bakia[a-z0-9]{16}\b",
    r"\beyj[a-z0-9_-]{10,}\.[a-z0-9_-]{10,}\.[a-z0-9_-]{10,}\b",
    r"\b(?:api[_ -]?key|secret[_ -]?key|database[_ -]?url|password)\s*[:=]\s*[^\s,;]{8,}",
    r"-----begin [^-]*private key-----",
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    without_marks = without_marks.replace("\u0111", "d").replace("\u0110", "D")
    without_marks = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", without_marks)
    return without_marks.casefold().strip()


def _normalized_variants(text: str) -> tuple[str, ...]:
    normalized = _normalize(text)
    canonical = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    leetspeak = normalized.translate(str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}))
    leetspeak = re.sub(r"[^a-z0-9]+", " ", leetspeak).strip()
    collapsed = re.sub(r"(.)\1{2,}", r"\1\1", leetspeak)
    return tuple(dict.fromkeys((normalized, canonical, leetspeak, collapsed)))


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(
        re.search(pattern, variant, flags=re.IGNORECASE | re.DOTALL)
        for variant in _normalized_variants(text)
        for pattern in patterns
    )


def _compact_variants(text: str) -> tuple[str, ...]:
    return tuple(re.sub(r"[^a-z0-9]", "", variant) for variant in _normalized_variants(text))


def _contains_compact_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in compact for compact in _compact_variants(text) for term in terms)


def _sensitive_decision(text: str) -> GuardrailDecision | None:
    for category, reason, patterns in _SENSITIVE_CATEGORIES:
        compact_terms = _COMPACT_SENSITIVE_TERMS.get(category, ())
        if _matches_any(text, patterns) or _contains_compact_term(text, compact_terms):
            return _refusal(category, reason)
    return None


def _refusal(category: str, reason: str) -> GuardrailDecision:
    return GuardrailDecision(
        allowed=False,
        category=category,
        reason=reason,
        response=(
            f"Orbit t\u1eeb ch\u1ed1i y\u00eau c\u1ea7u n\u00e0y v\u00ec n\u1ed9i dung li\u00ean quan \u0111\u1ebfn {reason}. "
            "Y\u00eau c\u1ea7u n\u1eb1m ngo\u00e0i ph\u1ea1m vi h\u1ed7 tr\u1ee3 an to\u00e0n c\u1ee7a h\u1ec7 th\u1ed1ng. Orbit ch\u1ec9 h\u1ed7 tr\u1ee3 c\u00f4ng vi\u1ec7c, "
            "l\u1ecbch, nhi\u1ec7m v\u1ee5, nh\u1eafc nh\u1edf, ghi nh\u1edb v\u00e0 x\u1eed l\u00fd h\u1ed9i tho\u1ea1i ph\u1ee5c v\u1ee5 c\u00f4ng vi\u1ec7c."
        ),
    )


def evaluate_request(text: str, *, conversation_mode: bool = False) -> GuardrailDecision:
    """Classify one user request before any LLM or tool is called."""
    if _matches_any(text, _INJECTION_PATTERNS) or _contains_compact_term(text, _COMPACT_INJECTION_TERMS):
        return _refusal(
            "prompt_injection",
            "d\u1ea5u hi\u1ec7u c\u1ed1 ghi \u0111\u00e8 ch\u1ec9 d\u1eabn, v\u01b0\u1ee3t guardrail ho\u1eb7c y\u00eau c\u1ea7u ti\u1ebft l\u1ed9 prompt h\u1ec7 th\u1ed1ng",
        )

    sensitive = _sensitive_decision(text)
    if sensitive is not None:
        return sensitive

    if _matches_any(text, _WORK_DOMAIN_PATTERNS):
        return GuardrailDecision(
            True, "work", "Y\u00eau c\u1ea7u thu\u1ed9c domain c\u00f4ng vi\u1ec7c c\u1ee7a Orbit.", ""
        )
    if _matches_any(text, _SMALL_TALK_PATTERNS):
        return GuardrailDecision(True, "small_talk", "T\u01b0\u01a1ng t\u00e1c x\u00e3 giao an to\u00e0n.", "")

    # ``conversation_mode`` is passed onward to the semantic classifier by guardrail_node. Access
    # to a conversation is permission to analyse that chat, not blanket permission for unrelated
    # questions, so it must no longer auto-allow everything here.
    return _refusal(
        "out_of_domain",
        "ch\u1ee7 \u0111\u1ec1 ngo\u00e0i domain c\u00f4ng vi\u1ec7c v\u00e0 x\u1eed l\u00fd h\u1ed9i tho\u1ea1i c\u1ee7a Orbit",
    )


def evaluate_request_with_history(
    text: str,
    *,
    previous_user_text: str = "",
    previous_assistant_text: str = "",
    conversation_mode: bool = False,
) -> GuardrailDecision:
    """Classify a request while preserving safe elliptical follow-ups in one thread.

    Hard policy checks always run on the new message first. History is consulted only when the
    new message was rejected solely as out-of-domain, the preceding user request was a valid work
    request, and the new text looks like a short answer to a time/choice clarification. This keeps
    "7 ng\u00e0y tr\u01b0\u1edbc" working without allowing an unrelated question to inherit permission from an
    earlier work turn.
    """
    decision = evaluate_request(text, conversation_mode=conversation_mode)
    if decision.allowed or decision.category != "out_of_domain":
        return decision
    if not previous_user_text or len(text) > 300 or not _matches_any(text, _FOLLOW_UP_PATTERNS):
        return decision

    previous = evaluate_request(previous_user_text, conversation_mode=conversation_mode)
    if not previous.allowed or previous.category not in {"work", "conversation"}:
        return decision

    is_time_or_reference = _matches_any(text, _FOLLOW_UP_PATTERNS[:-2] + (_FOLLOW_UP_PATTERNS[-1],))
    assistant_asked = _matches_any(previous_assistant_text, _CLARIFYING_QUESTION_PATTERNS)
    if not is_time_or_reference and not assistant_asked:
        return decision

    return GuardrailDecision(
        True,
        "work_follow_up",
        "C\u00e2u tr\u1ea3 l\u1eddi ti\u1ebfp n\u1ed1i m\u1ed9t y\u00eau c\u1ea7u c\u00f4ng vi\u1ec7c h\u1ee3p l\u1ec7 trong c\u00f9ng thread.",
        "",
    )


def evaluate_context(text: str) -> GuardrailDecision:
    """Apply hard sensitive-topic checks to conversation data.

    Prompt-injection-looking lines are redacted separately rather than causing
    the whole conversation to fail; this lets users safely summarize a chat in
    which somebody attempted an injection.
    """
    sensitive = _sensitive_decision(text)
    if sensitive is not None:
        return sensitive
    return GuardrailDecision(
        True, "conversation_data", "D\u1eef li\u1ec7u h\u1ed9i tho\u1ea1i \u0111\u01b0\u1ee3c ph\u00e9p.", ""
    )


def evaluate_action_content(text: str) -> GuardrailDecision:
    """Validate tool arguments immediately before a state-changing action.

    This is deliberately separate from domain classification: an ordinary event title such as
    "Dentist" may be valid even though it contains no work keyword. Injection and sensitive or
    illegal objectives still fail closed, including edits made during confirmation.
    """
    if _matches_any(text, _INJECTION_PATTERNS) or _contains_compact_term(text, _COMPACT_INJECTION_TERMS):
        return _refusal(
            "prompt_injection",
            "d\u1ea5u hi\u1ec7u c\u1ed1 ghi \u0111\u00e8 ch\u1ec9 d\u1eabn ho\u1eb7c l\u1ee3i d\u1ee5ng n\u1ed9i dung c\u1ee7a c\u00f4ng c\u1ee5 \u0111\u1ec3 \u0111i\u1ec1u khi\u1ec3n h\u1ec7 th\u1ed1ng",
        )
    sensitive = _sensitive_decision(text)
    if sensitive is not None:
        return sensitive
    return GuardrailDecision(True, "safe_action", "N\u1ed9i dung h\u00e0nh \u0111\u1ed9ng \u0111\u1ea1t guardrail.", "")


def evaluate_output(text: str) -> GuardrailDecision:
    """Fail closed if generated output leaks secrets/prompts or unsafe instructions."""
    if _matches_any(text, _SECRET_OUTPUT_PATTERNS):
        return _refusal(
            "secret_leakage", "th\u00f4ng tin x\u00e1c th\u1ef1c ho\u1eb7c b\u00ed m\u1eadt h\u1ec7 th\u1ed1ng"
        )
    if _matches_any(
        text,
        (
            r"\b(my|the) system prompt (is|says|:)\b",
            r"\bdeveloper (message|instruction) (is|says|:)\b",
            r"\bprompt he thong (la|noi|:)\b",
            r"<\s*(system|developer)(?:\s|>)",
            r"\bnon-negotiable safety and domain policy\b",
        ),
    ):
        return _refusal("prompt_leakage", "n\u1ed9i dung prompt ho\u1eb7c ch\u1ec9 d\u1eabn n\u1ed9i b\u1ed9")
    sensitive = _sensitive_decision(text)
    if sensitive is not None:
        return sensitive
    return GuardrailDecision(True, "safe_output", "Ph\u1ea3n h\u1ed3i \u0111\u1ea1t guardrail.", "")


def sanitize_untrusted_text(text: str) -> str:
    """Escape delimiters and redact obvious prompt-injection lines in user data."""
    safe_lines: list[str] = []
    truncated = (text or "")[:MAX_UNTRUSTED_TEXT_CHARS]
    for line in truncated.splitlines():
        if _matches_any(line, _INJECTION_PATTERNS) or _contains_compact_term(line, _COMPACT_INJECTION_TERMS):
            safe_lines.append("[\u0110\u00e3 \u1ea9n m\u1ed9t d\u00f2ng c\u00f3 d\u1ea5u hi\u1ec7u prompt injection]")
            continue
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_lines.append(escaped)
    if len(text or "") > MAX_UNTRUSTED_TEXT_CHARS:
        safe_lines.append(
            "[D\u1eef li\u1ec7u \u0111\u00e3 \u0111\u01b0\u1ee3c c\u1eaft b\u1edbt v\u00ec v\u01b0\u1ee3t gi\u1edbi h\u1ea1n an to\u00e0n]"
        )
    return "\n".join(safe_lines)


def wrap_untrusted_text(text: str, *, label: str = "conversation_data") -> str:
    safe_label = re.sub(r"[^a-z0-9_-]", "_", label.lower())
    return f"<{safe_label}>\n{sanitize_untrusted_text(text)}\n</{safe_label}>"
