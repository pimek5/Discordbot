# SPECIAL BET Feature

## Co to jest SPECIAL BET?

SPECIAL BET to specjalny rodzaj zakładu w systemie HEXBET, który daje **1.5x bonus na wygrane**.

## Jak uzyskać SPECIAL BET?

SPECIAL BET pojawia się gdy admin używa komendy `/hxfind` z parametrem `nickname`:

```
/hxfind nickname:Caps#EUW platform:euw1
```

Ta komenda:
1. Znajduje aktualną grę gracza o podanym nicku
2. Tworzy zakład z oznaką ⭐ **SPECIAL BET**
3. Wyświetla gracza jako 🎯 **Featured**

## Jak działa bonus?

### Przykład 1: Normalny bet
- Stawka: 100 tokenów
- Odds: 2.0x
- **Wygrana: 200 tokenów** (100 × 2.0)

### Przykład 2: SPECIAL BET
- Stawka: 100 tokenów
- Odds: 2.0x
- Bazowa wygrana: 200 tokenów
- **Bonus 1.5x: 300 tokenów** (200 × 1.5)

## Wizualne oznaczenia

SPECIAL BET jest wyraźnie oznaczony w embedzie:
- 🎯 **Featured:** [nazwa gracza]
- ⭐ **SPECIAL BET** - 1.5x bonus on winnings!
- Czerwony kolor embeda (#FF6B6B)

## Implementacja techniczna

### Database
- Kolumna `special_bet` w tabeli `hexbet_matches` (BOOLEAN, default FALSE)
- Ustawiana na TRUE tylko dla betów z `/hxfind nickname`

### Settlement
W funkcji `settle_match` sprawdzany jest flag `special_bet`:
```python
bonus_multiplier = 1.5 if is_special else 1.0
payout = int(base_payout * bonus_multiplier)
```

### Tworzenie betów
- `/hxfind nickname:X` → `special_bet=True`
- Featured task → `special_bet=False`
- Regular matches → `special_bet=False`

## Migracja

Uruchom migrację SQL:
```bash
psql $DATABASE_URL < tracker/HEXBET/migration_add_special_bet.sql
```

Lub ręcznie:
```sql
ALTER TABLE hexbet_matches ADD COLUMN IF NOT EXISTS special_bet BOOLEAN DEFAULT FALSE;
```
