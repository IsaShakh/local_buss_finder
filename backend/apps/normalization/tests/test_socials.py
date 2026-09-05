from apps.normalization.rules.socials import normalize_social_urls


def test_social_urls_preserve_provider_and_stable_first_seen_order():
    assert normalize_social_urls(
        {
            "instagram": (
                "HTTPS://Instagram.COM/alanya/#bio",
                "https://instagram.com/alanya/",
                "bad",
            ),
            "facebook": ("https://FACEBOOK.com/alanya?ref=page#about",),
        }
    ) == {
        "instagram": ("https://instagram.com/alanya/",),
        "facebook": ("https://facebook.com/alanya?ref=page",),
    }
