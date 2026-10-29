from django_filters import rest_framework as filters

from .models import Hall, Section, SportType, TrainingSession


class HallFilter(filters.FilterSet):
    class Meta:
        model = Hall
        fields = ("center", "sport_type")


class SectionFilter(filters.FilterSet):
    class Meta:
        model = Section
        fields = (
            "sport_type",
            "skill_level",
            "age_category",
        )


class TrainingSessionFilter(filters.FilterSet):
    sport_type = filters.ModelChoiceFilter(
        field_name="section__sport_type",
        queryset=SportType.objects.all(),
    )
    skill_level = filters.ChoiceFilter(
        field_name="section__skill_level",
        choices=Section._meta.get_field("skill_level").choices,
    )
    age_category = filters.ChoiceFilter(
        field_name="section__age_category",
        choices=Section._meta.get_field("age_category").choices,
    )
    starts_after = filters.IsoDateTimeFilter(
        field_name="starts_at",
        lookup_expr="gte",
    )
    starts_before = filters.IsoDateTimeFilter(
        field_name="starts_at",
        lookup_expr="lte",
    )

    class Meta:
        model = TrainingSession
        fields = (
            "section",
            "hall",
            "trainer",
        )