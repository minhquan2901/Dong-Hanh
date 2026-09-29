from fastapi.testclient import TestClient
from auth_service import register_user
from web_app import app

def test_account_and_report_flow(tmp_path, monkeypatch):
    monkeypatch.setattr('auth_service.USERS_FILE', tmp_path / 'users.json')
    monkeypatch.setattr('owner_service.USAGE_FILE', tmp_path / 'usage.json')
    monkeypatch.setattr('feedback_service.INBOX_FILE', tmp_path / 'inbox.json')
    monkeypatch.setenv('STUDYSYNC_SESSION_SECRET', 'test-session-secret-with-at-least-32-chars')
    monkeypatch.setenv('OWNER_USERNAME', 'site-owner')
    monkeypatch.setenv('OWNER_PASSWORD', 'owner-password-very-long')
    student = register_user('student01', 'old-pass', 'student', 'Tên cũ', '8/1')
    register_user('student02', 'other-pass', 'student', 'Người khác')
    client = TestClient(app)
    assert 'id="report-button"' in client.get('/account').text
    assert 'id="report-list"' in client.get('/owner').text
    assert 'href="/account#report"' in client.get('/student').text
    assert 'href="/account#report"' in client.get('/parent').text
    login = client.post('/api/auth/login', json={'username': 'student01', 'password': 'old-pass'})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['token']}
    assert 'password' not in client.get('/api/profile?username=student01', headers=headers).json()['user']
    assert client.get('/api/profile?username=student02', headers=headers).status_code == 401
    assert client.patch('/api/profile', json={'username': 'student02', 'full_name': 'Giả'}, headers=headers).status_code == 401
    assert client.patch('/api/profile', json={'username': 'student01', 'full_name': 'Tên mới', 'class_name': '8/1'}, headers=headers).json()['user']['full_name'] == 'Tên mới'
    assert client.post('/api/reports', json={'username': 'student02', 'category': 'bug', 'message': 'Lỗi trong trang chủ'}, headers=headers).status_code == 401
    assert client.post('/api/reports', json={'username': 'student01', 'category': 'bug', 'message': 'Lỗi trong trang chủ'}, headers=headers).status_code == 201
    assert client.get('/api/owner/reports', headers=headers).status_code == 401
    owner = client.post('/api/owner/login', json={'username': 'site-owner', 'password': 'owner-password-very-long'})
    owner_headers = {'Authorization': 'Bearer ' + owner.json()['token']}
    reports = client.get('/api/owner/reports', headers=owner_headers).json()['reports']
    assert reports[0]['username'] == 'student01'
    assert client.patch('/api/owner/reports/' + reports[0]['id'], json={'read': True}, headers=owner_headers).status_code == 200
    assert client.patch('/api/owner/users/' + student['id'], json={'full_name': 'Sửa tên'}, headers=headers).status_code == 401
    assert client.patch('/api/owner/users/' + student['id'], json={'full_name': 'Sửa tên'}, headers=owner_headers).status_code == 200
    assert client.post('/api/profile/password', json={'username': 'student01', 'current_password': 'wrong', 'new_password': 'new-pass'}, headers=headers).status_code == 400
    assert client.post('/api/profile/password', json={'username': 'student01', 'current_password': 'old-pass', 'new_password': 'new-pass'}, headers=headers).status_code == 200
    assert client.get('/api/profile?username=student01', headers=headers).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'student01', 'password': 'old-pass'}).status_code == 401
    new_login = client.post('/api/auth/login', json={'username': 'student01', 'password': 'new-pass'})
    assert new_login.status_code == 200
    new_headers = {'Authorization': 'Bearer ' + new_login.json()['token']}
    assert client.patch('/api/owner/users/' + student['id'] + '/status', json={'is_active': False}, headers=owner_headers).status_code == 200
    assert client.get('/api/profile?username=student01', headers=new_headers).status_code == 403
    assert client.post('/api/auth/login', json={'username': 'student01', 'password': 'new-pass'}).status_code == 401
