import re
from dataclasses import dataclass


@dataclass
class Verdict:
    allowed: bool
    reason: str = ""


SYSTEM_PROMPT = """\
Ты — ассистент-консультант по вопросам расторжения брака в РФ.

ГЛАВНОЕ ПРАВИЛО (соблюдай его строго): если пользователь только сообщил о
желании развестись или задал общий вопрос, но не указал деталей — НЕ давай
сразу развёрнутую инструкцию. Сначала задай ОДИН короткий уточняющий вопрос
и дождись ответа. Разворачивай полную рекомендацию только после того, как
уточнишь хотя бы один из этих моментов:
   - есть ли у пары общие несовершеннолетние дети;
   - согласны ли оба супруга на развод, или один из них против;
   - есть ли совместно нажитое имущество, которое нужно делить.

Пример правильного поведения:
Пользователь: "хочу развод"
Ты: "Сочувствую, что пришлось столкнуться с этим. Чтобы подсказать точнее —
скажите, у вас есть общие несовершеннолетние дети?"
(и только после ответа пользователя — переходишь к конкретным шагам)

Остальные правила:
1. Давай только общую справочную информацию.
2. Всегда указывай, что это не заменяет консультацию юриста.
3. Не помогай скрывать имущество или обманывать суд.
4. Если вопрос не про развод — вежливо откажись и попроси переформулировать.
"""

REFUSAL_MESSAGE = (
    "Не могу помочь с этим запросом ({reason}). "
    "Я отвечаю только на вопросы про развод и семейное право."
)

_HARD_BLOCK_PATTERNS = [
    r"как\s+(сделать|изготовить)\s+(бомб|оруж)",
    r"как\s+взломать",
    r"как\s+скрыть\s+имущество",
    r"однополы|одного пола|лгбт",
]

_BREEDING_SENSE = re.compile(
    r"развод(ить|ят|ишь|им|ите|ил[аи]?)(?!с[яь])"
    r"|развожу(?!с[яь])"
    r"|разведени[ея]"
    r"|разводчик"
)

_DIVORCE_CONTEXT = re.compile(
    r"брак|супруг|загс|раздел|имуществ|разошл|алимент"
    r"|муж|жена|жены|дет[иеья]|ребен|сын|дочь|суд|иск"
)

_OFF_TOPIC_OBJECT = re.compile(
    r"кролик|пчел|кур[ыаи]|птиц|скот|коров|коз[ыла]|рыб|собак|кошк|кошек"
    r"|хомяк|попугай|растени|цвет[ыао]|огород|грядк|саженц|рассад|дрожж"
)

_ANSWER_LIKE = re.compile(
    r"^\W*("
    r"да|нет|неа|ага|угу|конечно|разумеется|наверное|возможно|вроде"
    r"|не\s*знаю|без\s*поняти"
    r"|оба|обо[еи]|обоюдн|один|одна|одного|двое|трое|четверо|\d"
    r"|есть|нету|ничего|никак|только|пока|уже|ещ[её]"
    r"|против|согласн|за\b"
    r"|я\b|он\b|она\b|мы\b"
    r")"
)

_TOPIC_STEMS = (
    # сам развод
    "развод", "развест", "развел", "разойт", "разошл", "расторжен",
    # алименты и деньги
    "алимент", "содержан", "выплат", "пособи",
    # семья и стороны
    "брак", "супруг", "жена", "жены", "муж", "бывш", "семейн", "сожит",
    # дети
    "ребен", "дети", "детей", "детьми", "сын", "дочь", "дочер", "опек",
    "прожив", "несовершеннолет",
    # имущество
    "имуществ", "раздел", "квартир", "машин", "ипотек", "кредит",
    "недвижим", "нажит", "долев", "собственност", "дач", "гараж",
    "участок", "земельн", "автомобил", "вклад", "накоплен", "бизнес",
    # процедура
    "загс", "суд", "иск", "заявлен", "документ", "пошлин", "фамили",
    "свидетельств", "брачн", "юрист", "адвокат", "мировое",
    # вежливость
    "привет", "здравствуй", "добрый", "спасибо", "помог",
)

_ON_TOPIC_PATTERN = re.compile("|".join(re.escape(s) for s in _TOPIC_STEMS))

_WORD_SPLIT = re.compile(r"[^а-яa-z0-9]+")


def _normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def _prefix_distance(stem: str, word: str) -> int:
    previous = list(range(len(word) + 1))
    for i, stem_char in enumerate(stem, start=1):
        current = [i]
        for j, word_char in enumerate(word, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (stem_char != word_char),
                )
            )
        previous = current
    return min(previous)


def _allowed_typos(stem: str) -> int:
    if len(stem) <= 4:
        return 0
    if len(stem) <= 6:
        return 1
    return 2


def _looks_on_topic(text: str) -> bool:
    if _ON_TOPIC_PATTERN.search(text):
        return True

    words = [w for w in _WORD_SPLIT.split(text) if len(w) >= 3]
    for word in words:
        for stem in _TOPIC_STEMS:
            budget = _allowed_typos(stem)
            if budget and _prefix_distance(stem, word) <= budget:
                return True
    return False


def check_input(text: str) -> Verdict:
    low = _normalize(text)

    if any(re.search(p, low) for p in _HARD_BLOCK_PATTERNS):
        return Verdict(False, "запрещённая тема")

    on_topic = _looks_on_topic(low)

    same_root_other_topic = _BREEDING_SENSE.search(low) or _OFF_TOPIC_OBJECT.search(low)
    if same_root_other_topic and not _DIVORCE_CONTEXT.search(low):
        return Verdict(False, "вопрос не связан с темой развода")

    if on_topic:
        return Verdict(True)

    if len(low.split()) <= 4 and _ANSWER_LIKE.search(low):
        return Verdict(True)

    return Verdict(False, "вопрос не связан с темой развода")


def check_output(text: str) -> Verdict:
    low = _normalize(text)
    if any(re.search(p, low) for p in _HARD_BLOCK_PATTERNS):
        return Verdict(False, "ответ затронул запрещённую тему")
    return Verdict(True)