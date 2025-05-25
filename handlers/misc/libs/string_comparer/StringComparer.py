import Levenshtein

def calculate_similarity_percentage(str1: str, str2: str) -> float:
    """
    Рассчитывает процент схожести двух строк на основе расстояния Левенштейна.
    """
    distance = Levenshtein.distance(str1, str2)
    max_len = max(len(str1), len(str2))
    if max_len == 0:
        return 100.0  # Обе строки пустые
    similarity = (1 - distance / max_len) * 100
    return round(similarity, 2)

class StringComparer:
    """
    Класс для сравнения строк.
    """

    def partial_match(self, source_string: str, matching_string: str) -> float:
        """
        Выполняет частичный поиск.
        Сравнивает matching_string с подстроками source_string и находит
        наилучшее совпадение.
        """
        if not source_string or not matching_string:
            return 0.0

        best_match_percentage = 0.0

        # Итерируемся по всем возможным подстрокам source_string
        # такой же длины, как matching_string
        for i in range(len(source_string) - len(matching_string) + 1):
            substring = source_string[i : i + len(matching_string)]
            percentage = calculate_similarity_percentage(substring, matching_string)
            if percentage > best_match_percentage:
                best_match_percentage = percentage

        return best_match_percentage

    def full_match(self, source_string: str, matching_string: str) -> float:
        """
        Выполняет полный поиск.
        Сравнивает matching_string со всей source_string.
        """
        if not source_string or not matching_string:
            return 0.0
        return calculate_similarity_percentage(source_string, matching_string)