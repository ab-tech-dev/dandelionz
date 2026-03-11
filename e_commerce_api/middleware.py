import re
from django.conf import settings
from django.http import HttpResponseNotFound, HttpResponseForbidden


class BlockSuspiciousRequestsMiddleware:
    """
    Fast-fail known malicious/probing requests before URL resolution.
    Configure via settings:
    - BLOCKED_PATH_PREFIXES: list of path prefixes to block
    - BLOCKED_PATH_REGEXES: list of regex patterns to block
    - BLOCKED_METHODS: list of HTTP methods to block (e.g. TRACE)
    """

    DEFAULT_PREFIXES = [
        "/.env",
        "/.git",
        "/.hg",
        "/.svn",
        "/vendor/phpunit",
        "/phpunit",
        "/lib/phpunit",
        "/laravel/vendor/phpunit",
        "/www/vendor/phpunit",
        "/yii/vendor/phpunit",
        "/zend/vendor/phpunit",
        "/tests/vendor/phpunit",
        "/test/vendor/phpunit",
        "/testing/vendor/phpunit",
        "/api/vendor/phpunit",
        "/demo/vendor/phpunit",
        "/cms/vendor/phpunit",
        "/crm/vendor/phpunit",
        "/backup/vendor/phpunit",
        "/blog/vendor/phpunit",
        "/workspace/drupal/vendor/phpunit",
        "/panel/vendor/phpunit",
        "/public/vendor/phpunit",
        "/apps/vendor/phpunit",
        "/app/vendor/phpunit",
        "/containers/json",
        "/actuator",
        "/developmentserver",
        "/owa",
        "/guacamole",
    ]

    DEFAULT_REGEXES = [
        r"/phpunit/.*/eval-stdin\.php$",
        r"/vendor/.*phpunit.*/eval-stdin\.php$",
        r"/lib/.*phpunit.*/eval-stdin\.php$",
        r"/.*phpunit.*/eval-stdin\.php$",
        r"/\.env(\.|$)",
        r"/\.git/.*",
    ]

    DEFAULT_BLOCKED_METHODS = ["TRACE", "TRACK", "CONNECT"]

    def __init__(self, get_response):
        self.get_response = get_response
        self.blocked_prefixes = getattr(settings, "BLOCKED_PATH_PREFIXES", None) or self.DEFAULT_PREFIXES
        regexes = getattr(settings, "BLOCKED_PATH_REGEXES", None) or self.DEFAULT_REGEXES
        self.blocked_regexes = [re.compile(pattern) for pattern in regexes]
        self.blocked_methods = set(
            method.upper()
            for method in (getattr(settings, "BLOCKED_METHODS", None) or self.DEFAULT_BLOCKED_METHODS)
        )

    def __call__(self, request):
        if request.method.upper() in self.blocked_methods:
            return HttpResponseForbidden()

        path = request.path or ""
        if self._is_blocked_path(path):
            return HttpResponseNotFound()

        return self.get_response(request)

    def _is_blocked_path(self, path: str) -> bool:
        for prefix in self.blocked_prefixes:
            if path.startswith(prefix):
                return True
        for pattern in self.blocked_regexes:
            if pattern.search(path):
                return True
        return False
