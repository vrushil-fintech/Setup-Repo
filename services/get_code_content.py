import datetime
from fastapi import UploadFile
from app.dependencies import logger

class NoContentError(Exception):
    """Custom Exception for empty code file or pasted code."""
    pass

async def get_code_content(codefile: UploadFile = None, pasted_code: str = ""):
    if codefile:
        code_cont = (await codefile.read()).decode("utf-8")
        if code_cont.strip():
            return code_cont, codefile.filename
        else:
            logger.warning("Empty code file uploaded.")
            raise NoContentError("Empty code file.")
        
    elif pasted_code and pasted_code.strip():
        current_time = datetime.datetime.now()
        time_str = current_time.strftime("%H%M%S")  # Format time as hhmmss
        date_str = current_time.strftime("%m%d%y")  # Format date as mmddyy
        # filename = f"{time_str}_{date_str}_{user_id}.txt"
        file_name = f"{time_str}_{date_str}_7.txt"   # temporary user id 7
        return pasted_code.strip(), file_name
    
    else:
        logger.warning("Empty code file or pasted code.")
        raise NoContentError("No code file or code content provided.")