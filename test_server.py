import pytest
from server import app  # Your Flask app instance


@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Todo: Mock DB interactions.
    # For this basic test, we'll assume an empty DB or that the endpoint handles it gracefully.
    with app.test_client() as client:
        yield client


def test_get_elevated_dread_areas_unauthenticated(client):
    """Test the /api/get_elevated_dread_areas endpoint returns 200 OK."""
    response = client.get('/api/get_elevated_dread_areas')
    assert response.status_code == 200
    assert response.is_json
    # For now, just checking it loads and is JSON.
