def test_dabaoid_parse():
    from app.adapters.dabaoid import DabaoidAdapter
    sample_html = '''
    <div class="col-xs-3 col-md-3">
        <span class="badge bg-indigo text-indigo-fg">美国</span>
        状态: <span class="badge bg-green">正常</span>
        上次检查: 2026-07-30 00:00:00
        <button id="username_1" data-clipboard-text="testuser@outlook.com"></button>
        <button id="password_1" data-clipboard-text="testpass123"></button>
    </div>
    '''
    adapter = DabaoidAdapter()
    res = adapter.parse_html(sample_html)
    assert len(res) == 1
    assert res[0]["username"] == "testuser@outlook.com"
    assert res[0]["password"] == "testpass123"
    assert res[0]["region"] == "美国"
    assert res[0]["status"] == "normal"

def test_appstore_autos_parse():
    from app.adapters.appstore_autos import AppstoreAutosAdapter
    sample_json = {
        "accounts": [
            {
                "username": "apiuser@outlook.com",
                "password": "apipass123",
                "region_display": "台湾",
                "status": True,
                "message": "正常",
                "last_check": "2026-07-30 00:00:00"
            }
        ]
    }
    adapter = AppstoreAutosAdapter()
    res = adapter.parse_json(sample_json)
    assert len(res) == 1
    assert res[0]["username"] == "apiuser@outlook.com"
    assert res[0]["region"] == "台湾"
    assert res[0]["status"] == "normal"
