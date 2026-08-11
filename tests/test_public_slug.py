import pytest

from app.main import criar_slug_publico, normalizar_whatsapp


def test_public_slug_is_url_safe():
    slug = criar_slug_publico("Dra. María da Silva")
    assert slug.startswith("dra-maria-da-silva-")
    assert slug.replace("-", "").isalnum()


def test_public_slugs_are_not_reused():
    assert criar_slug_publico("Dra. Maria") != criar_slug_publico("Dra. Maria")


def test_normalizar_whatsapp():
    assert normalizar_whatsapp("+55 (81) 99999-0000") == "5581999990000"


def test_rejeita_whatsapp_curto():
    with pytest.raises(Exception):
        normalizar_whatsapp("123")
