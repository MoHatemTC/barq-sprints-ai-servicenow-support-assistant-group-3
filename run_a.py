from barq_support.worker import process_incident

SYS_ID = "47138238a9fe1981016e3762d1fd26d4"  #Run A — suggestAnswer  INC0000035
#SYS_ID = "bbc2e7c32fcf4b102e0e5b707fa4e3a3"  #Run B — requestHR      INC0010032
#SYS_ID = "bbc2e7c32fcf4b102e0e5b707fa4e3a3"  #Run C — failure recovery     INC0010032
#Run C كان اختبار فشل Qdrant على نفس INC0010032 ثم رجعنا شغلناه بنجاح.





print("=" * 70)
print("S3.4 - FULL TOOL-CALL TRACE")
print("=" * 70)

result = process_incident({"sys_id": SYS_ID})

print("\n" + "=" * 70)
print("EXECUTION SUMMARY")
print("=" * 70)

print(f"Iterations:        {result.get('s3_iterations')}")
print(f"Terminal called:   {result.get('s3_terminal_called')}")
print(f"Budget exhausted:  {result.get('s3_budget_exhausted', False)}")

print("\n" + "=" * 70)
print("FULL TOOL TRACE")
print("=" * 70)

for message in result.get("messages", []):
    if getattr(message, "type", None) != "ai":
        continue

    for tool_call in getattr(message, "tool_calls", []):
        name = tool_call.get("name")
        args = tool_call.get("args", {})

        print(f"\nTOOL: {name}")
        print("-" * 70)

        if name == "searchKB":
            print(f"Query: {args.get('query')}")

        elif name == "addWorkNote":
            print(f"Work note:\n{args.get('note')}")

        elif name == "suggestAnswer":
            print(f"Procedure:\n{args.get('procedure')}")
            print(f"\nSources: {args.get('sources')}")
            print(f"Confidence: {args.get('confidence')}")

        elif name == "requestHR":
            print(f"Reason:\n{args.get('reason')}")

    # Print tool results returned by the execution.
    if getattr(message, "type", None) == "tool":
        print(f"\nTOOL RESULT: {getattr(message, 'name', 'unknown')}")
        print("-" * 70)
        print(getattr(message, "content", ""))

print("\n" + "=" * 70)
print("FULL TRACE COMPLETED")
print("=" * 70)

