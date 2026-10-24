from datetime import date, timedelta

LOAN_PERIOD_DAYS = 14


class Loan:
    def __init__(self, id, book_id, member_id, due_date, loan_date=None, return_date=None, renewal_count=0):
        self.id = id
        self.book_id = book_id
        self.member_id = member_id
        self.loan_date = loan_date or date.today()
        self.due_date = due_date
        self.return_date = return_date
        self.renewal_count = renewal_count

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "member_id": self.member_id,
            "loan_date": self.loan_date.isoformat(),
            "due_date": self.due_date.isoformat(),
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "renewal_count": self.renewal_count,
        }

    @staticmethod
    def default_due_date():
        return date.today() + timedelta(days=LOAN_PERIOD_DAYS)
