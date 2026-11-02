import pytest
import time
from fastapi import HTTPException

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    seed_default_users,
    authenticate_user,
    get_current_user,
    require_admin
)
from app.db import run_migrations, get_db_connection
from app.main import login, LoginRequest, get_current_user_profile
from app.config import settings

@pytest.fixture
def auth_db(tmp_path):
    db_file = tmp_path / "auth_test.db"
    settings.db_path = str(db_file)
    run_migrations(custom_path=str(db_file))
    conn = get_db_connection(custom_path=str(db_file))
    seed_default_users(conn)
    conn.close()
    yield db_file

def test_password_hashing():
    pwd = "SecurePassword123!"
    h1, s1 = hash_password(pwd)
    h2, s2 = hash_password(pwd)
    
    # Salts should be unique
    assert s1 != s2
    assert h1 != h2
    
    # Verification should pass
    assert verify_password(pwd, h1, s1) is True
    assert verify_password("WrongPassword", h1, s1) is False

def test_jwt_token_lifecycle():
    token = create_access_token(user_id="usr_01", username="admin", role="admin", expires_in_minutes=5)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "usr_01"
    assert payload["username"] == "admin"
    assert payload["role"] == "admin"

def test_jwt_tampering_rejected():
    token = create_access_token(user_id="usr_01", username="admin", role="admin")
    parts = token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}wrongsig.{parts[2]}"
    assert decode_access_token(tampered_token) is None

def test_jwt_expiration():
    # Expired token (-1 minutes)
    token = create_access_token(user_id="usr_01", username="admin", role="admin", expires_in_minutes=-1)
    assert decode_access_token(token) is None

def test_api_login_success_and_role(auth_db):
    req = LoginRequest(username=settings.admin_user, password=settings.admin_password)
    res = login(req)
    assert res.access_token is not None
    assert res.role == "admin"
    assert res.username == settings.admin_user

def test_api_login_invalid_credentials_t15(auth_db):
    """T15: Access control - invalid login rejected."""
    req = LoginRequest(username=settings.admin_user, password="WrongPasswordHere")
    with pytest.raises(HTTPException) as exc_info:
        login(req)
    assert exc_info.value.status_code == 401
    assert "Incorrect" in exc_info.value.detail

def test_api_protected_profile_t15():
    """T15: Access control - verify user profile extraction."""
    user_payload = {"sub": "usr_01", "username": "admin", "role": "admin"}
    profile = get_current_user_profile(user=user_payload)
    assert profile["username"] == "admin"
    assert profile["role"] == "admin"

def test_require_admin_guard_t15():
    """T15: RBAC - require_admin rejects viewer role."""
    admin_user = {"sub": "usr_admin", "username": "admin", "role": "admin"}
    viewer_user = {"sub": "usr_viewer", "username": "viewer", "role": "viewer"}
    
    assert require_admin(admin_user) == admin_user
    
    with pytest.raises(HTTPException) as exc_info:
        require_admin(viewer_user)
    assert exc_info.value.status_code == 403
