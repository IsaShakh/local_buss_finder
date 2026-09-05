import pytest

from apps.normalization.rules.names import NameParts, normalize_name


@pytest.mark.parametrize(
    ("raw", "display", "normalized", "match"),
    [
        (
            "  Alanya Smile Diş Kliniği LTD. ŞTİ. ",
            "Alanya Smile Diş Kliniği",
            "alanya smile diş kliniği",
            "alanya smile dis klinigi",
        ),
        ("GÖZDE GÜZELLİK A.Ş.", "GÖZDE GÜZELLİK", "gözde güzellik", "gozde guzellik"),
    ],
)
def test_normalize_turkish_business_name(raw, display, normalized, match):
    assert normalize_name(raw) == NameParts(display, normalized, match)


def test_legal_suffix_is_removed_only_at_end_of_name():
    assert normalize_name("A.Ş. Yapı Market") == NameParts(
        "A.Ş. Yapı Market", "a.ş. yapı market", "a s yapi market"
    )
    assert normalize_name("A.Ş. Yapı Market A.Ş.") == NameParts(
        "A.Ş. Yapı Market", "a.ş. yapı market", "a s yapi market"
    )


@pytest.mark.parametrize(
    ("raw", "display"),
    [
        ("Akdeniz Turizm Ltd.", "Akdeniz Turizm"),
        ("Akdeniz Turizm Anonim Şirketi", "Akdeniz Turizm"),
    ],
)
def test_supported_terminal_legal_suffixes_are_removed(raw, display):
    assert normalize_name(raw).display_name == display
