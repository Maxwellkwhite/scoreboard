from __future__ import annotations

import os
from typing import Any

DEFAULT_PRESENTING_SPONSOR: dict[str, str] = {
    'name': 'EmailsConfirmed',
    'url': 'https://www.emailsconfirmed.com/',
    'logo_url': 'https://www.emailsconfirmed.com/static/images/logo.png',
    'tagline': 'The cheapest email verification tool',
}


def presenting_sponsor_context(_is_production: bool | None = None) -> dict[str, Any]:
    show = os.environ.get(
        'PRESENTING_SPONSOR_ENABLED', 'true'
    ).strip().lower() != 'false'

    name = os.environ.get('PRESENTING_SPONSOR_NAME', '').strip()
    logo_url = os.environ.get('PRESENTING_SPONSOR_LOGO_URL', '').strip()
    url = os.environ.get('PRESENTING_SPONSOR_URL', '').strip()
    tagline = os.environ.get('PRESENTING_SPONSOR_TAGLINE', '').strip()

    if show and not any((name, logo_url, url, tagline)):
        defaults = DEFAULT_PRESENTING_SPONSOR
        name = defaults['name']
        logo_url = defaults['logo_url']
        url = defaults['url']
        tagline = defaults['tagline']

    return {
        'presenting_sponsor': {
            'enabled': show,
            'name': name or None,
            'logo_url': logo_url or None,
            'url': url or None,
            'tagline': tagline or None,
        },
        'app_intro_text': os.environ.get(
            'APP_INTRO_TEXT',
            'Live scores with rich animated game cards for MLB and the World Cup. '
            'Follow today\'s games, standings, and match detail in one place.',
        ).strip(),
    }
