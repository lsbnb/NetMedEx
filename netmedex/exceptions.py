class EmptyInput(Exception):
    """Empty query or PMIDs"""

    def __init__(self, msg="Your search cannot be empty."):
        super().__init__(msg)


class NoArticles(Exception):
    """No articles found by PubTator3 API"""

    def __init__(self, msg="No articles found by PubTator3 API."):
        super().__init__(msg)


class UnsuccessfulRequest(Exception):
    """Unsuccessful request to PubTator3 API"""

    def __init__(self, msg="Unsuccessful request to PubTator3 API."):
        super().__init__(msg)
