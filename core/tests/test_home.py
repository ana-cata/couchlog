def test_placeholder_page_shows(client):
    response = client.get('/')

    assert response.status_code == 200
    assert 'Couchlog' in response.content.decode()
