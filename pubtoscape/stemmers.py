IRREGULAR_WORDS = {
    "species": "species"
}


def s_stemmer(word: str):
    subwords = word.split(" ")
    last_subword = subwords[-1]

    if last_subword in IRREGULAR_WORDS:
        return " ".join(subwords[:-1] + [IRREGULAR_WORDS[last_subword]])

    if last_subword.endswith("ies") and not last_subword.endswith(("eies", "aies")):
        word = word[:-3] + "y"
    elif last_subword.endswith("es") and not last_subword.endswith(("aes", "ees", "oes")):
        word = word[:-1]
    elif last_subword.endswith("s") and not last_subword.endswith(("is", "us", "ss")):
        word = word[:-1]

    return word
