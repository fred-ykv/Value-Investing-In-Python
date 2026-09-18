"""Optional integration check using the installed exchange calendar."""
from datetime import date
from fundamental_analysis.portfolio_runner import validate_calendar

days = [date(2020,7,1), date(2020,7,2), date(2020,7,6)]
print(validate_calendar(days, date(2020,7,1), date(2020,7,6)))
print(validate_calendar(days[:2], date(2020,7,1), date(2020,7,5)))
for wrong in (days[:-1], sorted(days + [date(2020,7,3)]), list(reversed(days))):
    try:
        validate_calendar(wrong, date(2020,7,1), date(2020,7,6))
    except ValueError:
        continue
    raise AssertionError("Calendario incorreto aceito")
print("Calendario real: feriado e sessao ausente rejeitados")

