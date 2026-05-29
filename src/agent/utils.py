def print_result(result) -> None:
    print(f"\n--- Antwoord (zekerheid: {result.confidence}) ---")
    print(result.answer)
    print("----------------------------------\n")


def print_messages(messages) -> None:
    for m in messages:
        print(m.kind)
        for p in m.parts:
            part_kind = p.part_kind
            if part_kind == "user-prompt":
                print("  USER:", p.content)
            if part_kind == "tool-call":
                print("  TOOL CALL:", p.tool_name, p.args)
            if part_kind == "tool-return":
                print("  TOOL RETURN:", p.tool_name)
            if part_kind == "text":
                print("  ASSISTANT:", p.content)
        print()
