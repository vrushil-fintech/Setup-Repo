from app.crud.refresh_tokens import get_refresh_token

async def verify_refresh_token(db_session, refresh_token: str, userid: str):
    if len(refresh_token) != 32:
        return False
    
    result = await get_refresh_token(db_session, refresh_token, userid)
    if(result):
        return True

    return False
    
