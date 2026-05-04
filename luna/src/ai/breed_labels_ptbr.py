"""Mapa de rótulos de raça: inglês (Stanford Dogs) → português brasileiro."""

BREED_LABELS_PTBR: dict[str, str] = {
    # Cães
    "golden_retriever": "Golden Retriever",
    "labrador_retriever": "Labrador Retriever",
    "german_shepherd": "Pastor Alemão",
    "bulldog": "Buldogue",
    "french_bulldog": "Buldogue Francês",
    "poodle": "Poodle",
    "beagle": "Beagle",
    "yorkshire_terrier": "Yorkshire Terrier",
    "shih-tzu": "Shih Tzu",
    "rottweiler": "Rottweiler",
    "dachshund": "Dachshund",
    "boxer": "Boxer",
    "maltese_dog": "Maltês",
    "siberian_husky": "Husky Siberiano",
    "doberman": "Dobermann",
    "border_collie": "Border Collie",
    "chihuahua": "Chihuahua",
    "pomeranian": "Lulu da Pomerânia",
    "dalmatian": "Dálmata",
    "cocker_spaniel": "Cocker Spaniel",
    "great_dane": "Grande Dinamarquês",
    "schnauzer": "Schnauzer",
    "saint_bernard": "São Bernardo",
    "samoyed": "Samoieda",
    "chow": "Chow Chow",
    "shar-pei": "Shar-Pei",
    "weimaraner": "Weimaraner",
    "vizsla": "Vizsla",
    "akita": "Akita",
    "shiba_inu": "Shiba Inu",
    # Gatos (uso interno — YOLO já separa dog/cat)
    "tabby": "Gato Malhado",
    "persian_cat": "Gato Persa",
    "siamese_cat": "Gato Siamês",
    "maine_coon": "Maine Coon",
    "british_shorthair": "British Shorthair",
}


def traduzir(label_en: str) -> str:
    """Retorna o nome em pt-BR ou o próprio label formatado se não encontrado."""
    return BREED_LABELS_PTBR.get(label_en, label_en.replace("_", " ").title())
