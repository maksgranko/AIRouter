error_filters = {
    "Failed to create temporary account. Status: 403": (506, "Провайдер вернул некорректный ответ, пожалуйста, попробуйте снова."),
    "You have reached your request limit for the hour. [Upgrade for higher rate limits]": (506, "Провайдер вернул некорректный ответ, пожалуйста, попробуйте снова."),
    "OPENSSL_internal:SSLV3_ALERT_HANDSHAKE_FAILURE": (506, "Провайдер вернул некорректный ответ, пожалуйста, попробуйте снова."),
    "RetryProviderError": (506, "Провайдер вернул некорректный ответ, пожалуйста, попробуйте снова.")
}

def check_string_for_errors(input_string):
    """
    Проверяет входную строку на наличие подстрок, определенных в error_filters.

    Args:
        input_string (str): Входная строка для проверки.

    Исключение:
        Exception: если найдено совпадение, выбрасывается исключение с кодом и сообщением.
    """
    for filter_string, error_info in error_filters.items():
        if filter_string in input_string:
            raise Exception(f"Код {error_info[0]}: {error_info[1]}")



if __name__ == "__main__":
    test_string_1 = "Это тестовая строка с Строка внутри."
    test_string_2 = "Это другая строка без ошибок."

    try:
        check_string_for_errors(test_string_1)
        print(f"Строка '{test_string_1}' не содержит известных ошибок.")
    except Exception as e:
        print(f"Строка '{test_string_1}' содержит ошибку: {e}")

    try:
        check_string_for_errors(test_string_2)
        print(f"Строка '{test_string_2}' не содержит известных ошибок.")
    except Exception as e:
        print(f"Строка '{test_string_2}' содержит ошибку: {e}")

class FilteredStreamContentException(Exception):
    def __init__(self, message):
        super().__init__(message)