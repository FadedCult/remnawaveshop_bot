from app.bot.texts import TEXTS


def tr(lang: str, key: str, **kwargs) -> str:
    raw = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return raw.format(**kwargs)

