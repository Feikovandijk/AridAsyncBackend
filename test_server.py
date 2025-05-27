import pytest
from server import app  # Your Flask app instance


@pytest.fixture
def client():
    app.config['TESTING'] = True
    # In a real test suite, you'd likely mock database interactions for most tests.
    # For this basic test, we'll assume an empty DB or that the endpoint handles it gracefully.
    with app.test_client() as client:
        yield client


def test_get_elevated_dread_areas_unauthenticated(client):
    """Test the /api/get_elevated_dread_areas endpoint returns 200 OK."""
    response = client.get('/api/get_elevated_dread_areas')
    assert response.status_code == 200
    # You could also assert that the response is valid JSON
    assert response.is_json
    # And that it returns an empty list or a list of dicts if you have initial data
    # For now, just checking it loads and is JSON is a good start.
    # Example: assert response.json == []  # if expecting an empty list with no dread 