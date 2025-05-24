import json

from handlers.misc import finder
import logging
async def reformat_messages(input_json):
    data = json.loads(input_json)
    messages = data.get('messages', [])

    if not messages:
        raise ValueError("Список сообщений не может быть пустым")
    if messages[-1]['role'] != 'user':
        raise ValueError("Последнее сообщение должно быть от пользователя")

    first_message = messages[0]['content']

    main_prompt = ("YOU ARE A LARGE LANGUAGE MODEL. YOUR TASK IS TO EITHER CORRECTLY ANSWER THE USER'S QUESTION OR CORRECTLY PERFORM THE USER'S REQUESTED ACTION. USE THE INFORMATION PROVIDED BELOW. CAREFULLY READ THE <CURRENT_USER_MESSAGE> BLOCK AND RESPOND TO IT APPROPRIATELY. ALSO, PAY ATTENTION TO THE <CURRENT_SYSTEM_MESSAGE> BLOCK IF IT IS PRESENT. WHILE DOING SO, TAKE INTO ACCOUNT THE ENTIRE CONVERSATION HISTORY INSIDE THE <YOUR_CONTEXT> BLOCK. \n"
                   "IF AN <INSTRUCTIONS> BLOCK IS PRESENT, YOU MUST STRICTLY FOLLOW THE INSTRUCTIONS CONTAINED WITHIN IT. DO NOT IGNORE ANY INSTRUCTIONS. ALWAYS PRIORITIZE THEM WHEN GENERATING YOUR RESPONSE. \n"
                   "IF THE <INSTRUCTIONS> BLOCK REFERS TO TOOLS OR EXTERNAL ACTIONS (E.G., WEB SEARCH, IMAGE GENERATION, PYTHON CODE EXECUTION), YOU MUST ACTIVELY USE THE APPROPRIATE TOOL(S) TO FULFILL THE REQUEST UNLESS OTHERWISE EXPLICITLY RESTRICTED. \n"
                   "DO NOT ATTEMPT TO MANUALLY SIMULATE TOOL OUTPUT. INSTEAD, CALL THE TOOL DIRECTLY. \n"
                   "ALWAYS DEFAULT TO TOOL USE WHEN IT CAN YIELD A MORE ACCURATE, UP-TO-DATE, OR HIGH-FIDELITY RESULT.\n\n\n\n"
                   )
    before_context = "THE <YOUR_CONTEXT> BLOCK CONTAINS ALL PREVIOUS MESSAGES FROM THE CURRENT CONVERSATION SESSION ARRANGED IN CHRONOLOGICAL ORDER (OLDEST TO NEWEST) - YOU MUST CAREFULLY REVIEW THIS HISTORY TO UNDERSTAND THE CONVERSATION FLOW, IDENTIFY RECURRING THEMES, TRACK USER PREFERENCES AND REQUESTS, REFERENCE SPECIFIC DETAILS FROM EARLIER EXCHANGES, AVOID REPEATING INFORMATION ALREADY PROVIDED, BUILD UPON ESTABLISHED CONTEXT, AND ENSURE YOUR CURRENT RESPONSE IS CONSISTENT WITH AND INFORMED BY THE ENTIRE CONVERSATION THREAD.\n\n"
    before_instructions = ""
    instructions = ""
    instructions_exists = False
    if 'cline' in first_message.lower() or 'roo' in first_message.lower():
        instructions = f"<INSTRUCTIONS>{first_message.strip()}</INSTRUCTIONS>\n\n"
        messages.pop(0)
        instructions_exists = True
    user_length = 0
    
    context_blocks = []
    if len(messages)>1:
        for msg in messages[:-1]:
            role = msg['role']
            content = msg['content'].strip()
            context_blocks.append(f"<role:{role}>{content}</role:{role}>")
            if role == 'user':
                user_length += 1

    context_section = "<YOUR_CONTEXT>\n" + "\n".join(context_blocks) + "\n</YOUR_CONTEXT>\n\n"
    logging.info("Instructions: " + str(instructions_exists))
    if instructions_exists:
        before_instructions = "THE <INSTRUCTIONS> BLOCK CONTAINS CRITICAL DIRECTIVES THAT OVERRIDE ALL OTHER GUIDANCE AND HAVE ABSOLUTE PRIORITY - YOU MUST FOLLOW EVERY INSTRUCTION EXACTLY AS WRITTEN, USE ALL REQUIRED TOOLS ACTIVELY (NEVER SIMULATE TOOL OUTPUT), COMPLETE ALL SPECIFIED TASKS WITHOUT OMISSION, AND PRIORITIZE INSTRUCTIONS OVER CONVERSATION HISTORY OR GENERAL GUIDELINES.\n"
    if instructions_exists and len(messages) > 2: 
        logging.info("Instructions + messages length > 2 ")
        current_user_message = messages[-1]['content'].strip()
        user_section = f"<CURRENT_SYSTEM_MESSAGE>\n{current_user_message}\n</CURRENT_SYSTEM_MESSAGE>"
    elif instructions_exists:
        user_section = f"<CURRENT_USER_MESSAGE>\n{finder.find_between_r(first_message,"<task>","</task>")}\n</CURRENT_USER_MESSAGE>"
    else:
        current_user_message = messages[-1]['content'].strip()
        user_section = f"<CURRENT_USER_MESSAGE>\n{current_user_message}\n</CURRENT_USER_MESSAGE>"
    print(user_section)
    final_message = main_prompt + user_section + before_context + context_section + before_instructions + instructions 
    
    data['messages'] = [
        {
            "role": "user",
            "content": final_message
        }
    ]
    return json.dumps(data, ensure_ascii=False, indent=4)