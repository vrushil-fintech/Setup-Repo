async def call_gemini(i, characteristic, prompt, code_content, model):
    try:
        parsing_prompt = code_content + "\n" + prompt
    except Exception as e:
        print(
            f"Error constructing parsing prompt for Coroutine-{i} ~ {characteristic}: {e}"
        )
        return  # Exit the function early if parsing_prompt cannot be constructed
    
    yield f"\n# {characteristic}\n"
    
    try:
        response = await model.generate_content_async(parsing_prompt, stream=True)
        async for chunk in response:
            if chunk.text is not None:
                yield chunk.text
    except Exception as e:
        print(f"Error calling model API for Coroutine-{i} ~ {characteristic}: {e}")
        return  # Exit the function early if the API call fails

    # For storing responses to a file locally

    # try:
    #     # Writing to file, ensuring file operations are handled within try-except to catch any IO errors
    #     async with aiofiles.open(cache_file_path, "a", encoding="utf-8") as file:
    #         await file.write(f"\n## {characteristic}\n")
    #         await file.write(response.text)
    # except Exception as e:
    #     print(f"Error writing to file for Coroutine-{i} ~ {characteristic}: {e}")
    #     return  # Optionally handle cleanup or further error reporting

    print(f"Coroutine-{i} ~ {characteristic} finished writing to the file.")