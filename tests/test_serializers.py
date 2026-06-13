from app.api.serializers import exercise_dict, image_url
from app.core.models import Exercise


def exercise() -> Exercise:
    return Exercise(
        id="3_4_Sit-Up",
        name="3/4 Sit-Up",
        level="beginner",
        force="pull",
        mechanic="compound",
        equipment="body only",
        category="strength",
        primary_muscles=["abdominals"],
        secondary_muscles=[],
        instructions=["Lie down and curl your torso under control."],
        instructions_generated=False,
        images=["3_4_Sit-Up/0.jpg"],
        muscle_groups=["abs"],
    )


def test_image_url_uses_imagekit_domain() -> None:
    assert image_url("3_4_Sit-Up/0.jpg") == "https://ik.imagekit.io/yuhonas/3_4_Sit-Up/0.jpg"


def test_exercise_dict_includes_raw_paths_and_image_urls() -> None:
    payload = exercise_dict(exercise())

    assert payload["images"] == ["3_4_Sit-Up/0.jpg"]
    assert payload["image_urls"] == ["https://ik.imagekit.io/yuhonas/3_4_Sit-Up/0.jpg"]
