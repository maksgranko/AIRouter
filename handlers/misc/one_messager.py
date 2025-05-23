import json

async def reformat_messages(input_json):
    data = json.loads(input_json)
    messages = data.get('messages', [])
    
    # Проверяем, что список не пустой и последнее сообщение от пользователя
    if not messages:
        raise ValueError("Список сообщений не может быть пустым")
    if messages[-1]['role'] != 'user':
        raise ValueError("Последнее сообщение должно быть от пользователя")
    
    # Если сообщение одно, оставляем как есть
    if len(messages) == 1:
        new_messages = messages
    else:
        # Собираем контекст из всех сообщений, кроме последнего
        context = "\n".join(
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in messages[:-1]
        )
        # Берём последнее сообщение как вопрос
        main_task = messages[-1]['content']
        # Оборачиваем всё в одно сообщение
        wrapped_content = (
            "Previous conversation (for context only):\n\n"
            + context
            + "\n\n---\n\nUser's current question: "
            + main_task
        )
        new_messages = [{"role": "user", "content": wrapped_content}]
    
    data['messages'] = new_messages
    return json.dumps(data, ensure_ascii=False, indent=4)