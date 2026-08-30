# Testing web interface (offline)

import webapp


# Tests that root route directs to page
def test_index_page_is_served():
    client = webapp.app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'Rug-Pull Detector' in response.data