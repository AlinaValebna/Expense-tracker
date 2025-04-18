from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)
import os
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(os.path.join(os.getcwd(), 'expenses.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key_here'

# Extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)

    expenses = db.relationship('Expense', backref='owner', lazy=True)
    saving_goals = db.relationship('SavingGoal', backref='owner', lazy=True)
    incomes = db.relationship('Income', backref='owner', lazy=True)
    category_budgets = db.relationship('CategoryBudget', backref='owner', lazy=True)
    wealth_note = db.relationship('WealthNote', backref='owner', uselist=False)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class SavingGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    saved_amount = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class CategoryBudget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    limit = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class WealthNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

category_icons = {
    "Food": "🍔",
    "Transport": "🚗",
    "Entertainment": "🎮",
    "Bills": "💡",
    "Health": "💊",
    "Shopping": "🛍️",
    "Other": "💸"
}
# Routes
@app.route('/')
@login_required
def index():
    filter_option = request.args.get('filter', 'all')
    expenses_query = Expense.query.filter_by(user_id=current_user.id)
    now = datetime.utcnow()
    category_icons = {
        "Food": "🍔",
        "Transport": "🚗",
        "Entertainment": "🎮",
        "Bills": "💡",
        "Health": "💊",
        "Shopping": "🛍️",
        "Other": "💸"
    }

    if filter_option == 'month':
        expenses_query = expenses_query.filter(
            extract('month', Expense.date) == now.month,
            extract('year', Expense.date) == now.year
        )
    elif filter_option == 'week':
        week_ago = now - timedelta(days=7)
        expenses_query = expenses_query.filter(Expense.date >= week_ago)

    expenses = expenses_query.order_by(Expense.date.desc()).all()
    total_expenses = sum(e.amount for e in expenses)

    income_this_month = (
        db.session.query(func.sum(Income.amount))
        .filter_by(user_id=current_user.id)
        .filter(extract('month', Income.date) == now.month)
        .filter(extract('year', Income.date) == now.year)
        .scalar() or 0.0
    )

    net_balance = income_this_month - total_expenses

    goals = SavingGoal.query.filter_by(user_id=current_user.id).order_by(SavingGoal.id.desc()).limit(3).all()

    category_totals = defaultdict(float)
    for expense in expenses:
        category_totals[expense.category] += expense.amount
    chart_labels = list(category_totals.keys())
    chart_data = [round(amount, 2) for amount in category_totals.values()]
    note = WealthNote.query.filter_by(user_id=current_user.id).first()
    note_text = note.text if note else ''

    return render_template(
        'index.html',
        expenses=expenses,
        total_expenses=total_expenses,
        income=income_this_month,
        net=net_balance,
        filter=filter_option,
        goals=goals,
        chart_labels=chart_labels,
        chart_data=chart_data,
        category_icons=category_icons,
        note_text=note_text
    )



@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        description = request.form['description']
        category = request.form['category']

        new_expense = Expense(
            amount=amount,
            description=description,
            category=category,
            user_id=current_user.id
        )
        db.session.add(new_expense)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_expense.html')

@app.route('/delete/<int:expense_id>')
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.owner != current_user:
        return "Unauthorized"
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            hashed_password = generate_password_hash(password)

            if User.query.filter_by(email=email).first():
                return "Email already registered."

            new_user = User(username=username, email=email, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except Exception as e:
            return f"Registration error: {e}"  # ⛑️ Show error in browser
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        return "Invalid email or password."
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    if request.method == 'POST':
        name = request.form['name']
        target = float(request.form['target'])
        goal = SavingGoal(name=name, target_amount=target, user_id=current_user.id)
        db.session.add(goal)
        db.session.commit()
        return redirect(url_for('goals'))
    goals = SavingGoal.query.filter_by(user_id=current_user.id).all()
    return render_template('goals.html', goals=goals)

@app.route('/add_saving/<int:goal_id>', methods=['POST'])
@login_required
def add_saving(goal_id):
    goal = SavingGoal.query.get_or_404(goal_id)
    if goal.owner != current_user:
        return "Unauthorized"
    amount = float(request.form['amount'])
    goal.saved_amount += amount
    db.session.commit()
    return redirect(url_for('goals'))

@app.route('/delete_goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_goal(goal_id):
    goal = SavingGoal.query.get_or_404(goal_id)
    if goal.owner != current_user:
        return "Unauthorized"
    db.session.delete(goal)
    db.session.commit()
    return redirect(url_for('goals'))


@app.route('/income', methods=['GET', 'POST'])
@login_required
def income():
    if request.method == 'POST':
        source = request.form['source']
        amount = float(request.form['amount'])
        new_income = Income(source=source, amount=amount, user_id=current_user.id)
        db.session.add(new_income)
        db.session.commit()
        return redirect(url_for('income'))
    incomes = Income.query.filter_by(user_id=current_user.id).order_by(Income.date.desc()).all()
    total_income = sum(i.amount for i in incomes)
    return render_template('income.html', incomes=incomes, total_income=total_income)

@app.route('/budgets', methods=['GET', 'POST'])
@login_required
def budgets():
    if request.method == 'POST':
        category = request.form['category']
        limit = float(request.form['limit'])
        existing = CategoryBudget.query.filter_by(user_id=current_user.id, category=category).first()
        if existing:
            existing.limit = limit
        else:
            budget = CategoryBudget(category=category, limit=limit, user_id=current_user.id)
            db.session.add(budget)
        db.session.commit()
        return redirect(url_for('budgets'))

    budgets = CategoryBudget.query.filter_by(user_id=current_user.id).all()
    now = datetime.utcnow()
    expenses_by_category = db.session.query(
        Expense.category, func.sum(Expense.amount)
    ).filter_by(user_id=current_user.id).filter(
        extract('month', Expense.date) == now.month,
        extract('year', Expense.date) == now.year
    ).group_by(Expense.category).all()
    expense_dict = dict(expenses_by_category)
    return render_template('budgets.html', budgets=budgets, expenses=expense_dict)

@app.route('/add_wealth_note', methods=['POST'])
@login_required
def add_wealth_note():
    note = WealthNote.query.filter_by(user_id=current_user.id).first()
    if not note:
        note = WealthNote(user_id=current_user.id)
        db.session.add(note)
    note.text = request.form['text']
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/init-db')
def init_db():
    with app.app_context():
        db.create_all()
    return "✅ Database tables created!"

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)