"""
NEPSE AI Trading Bot — MySQL Database Manager
===============================================
Handles persistent storage of accounts, transaction ledger,
holdings, fees (Broker, SEBON, DP, CGT), and TMS transaction logs in MySQL.
"""

import os
import json
import logging
import pymysql
from datetime import datetime

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'mysql_config.json')


class DatabaseManager:
    def __init__(self):
        self.config = self._load_config()
        self.connected = False
        self._init_db()

    def _load_config(self):
        default_config = {
            'host': os.environ.get('MYSQL_HOST', 'localhost'),
            'port': int(os.environ.get('MYSQL_PORT', 3306)),
            'user': os.environ.get('MYSQL_USER', 'root'),
            'password': os.environ.get('MYSQL_PASSWORD', ''),
            'database': os.environ.get('MYSQL_DATABASE', 'nepse_trading_db'),
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                    default_config.update(saved)
            except Exception as e:
                logger.warning(f"Failed to read {CONFIG_FILE}: {e}")
        return default_config

    def save_config(self, new_config):
        """Save MySQL connection parameters and re-initialize connection."""
        self.config.update(new_config)
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            self._init_db()
            return {'success': self.connected, 'message': 'MySQL connected successfully' if self.connected else 'Could not connect with provided credentials'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_connection(self, select_db=True):
        """Get PyMySQL connection."""
        return pymysql.connect(
            host=self.config['host'],
            port=int(self.config['port']),
            user=self.config['user'],
            password=self.config['password'],
            database=self.config['database'] if select_db else None,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=3
        )

    def test_connection(self, host=None, port=None, user=None, password=None, database=None):
        """Test MySQL connection with given or current credentials."""
        h = host or self.config['host']
        p = int(port or self.config['port'])
        u = user or self.config['user']
        pw = password if password is not None else self.config['password']
        db = database or self.config['database']

        try:
            conn = pymysql.connect(
                host=h, port=p, user=u, password=pw,
                connect_timeout=3
            )
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION();")
                version = cur.fetchone()
            conn.close()
            return {'success': True, 'version': list(version.values())[0] if version else 'MySQL'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _init_db(self):
        """Create database and tables in MySQL if they do not exist."""
        try:
            # Step 1: Connect to server without database to create database
            conn = self.get_connection(select_db=False)
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self.config['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            conn.close()

            # Step 2: Connect to database and create schema
            conn = self.get_connection(select_db=True)
            with conn.cursor() as cur:
                # Accounts Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS `accounts` (
                    `id` VARCHAR(50) PRIMARY KEY,
                    `name` VARCHAR(100) NOT NULL,
                    `broker_id` VARCHAR(50) DEFAULT 'TMS-29',
                    `client_code` VARCHAR(50) DEFAULT 'CLIENT-001',
                    `cash_balance` DECIMAL(15,2) DEFAULT 0.00,
                    `initial_fund` DECIMAL(15,2) DEFAULT 0.00,
                    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB;
                """)

                # Initialize default account if empty
                cur.execute("SELECT COUNT(*) AS cnt FROM `accounts`;")
                if cur.fetchone()['cnt'] == 0:
                    cur.execute("""
                    INSERT INTO `accounts` (`id`, `name`, `broker_id`, `client_code`, `cash_balance`, `initial_fund`)
                    VALUES ('primary', 'Main Trading Account', 'Broker-29', 'NEPSE-TMS29', 0.00, 0.00);
                    """)
                else:
                    # Clean up old dummy 100,000 cash balance if present
                    cur.execute("""
                    UPDATE `accounts` 
                    SET `cash_balance` = 0.00, `initial_fund` = 0.00 
                    WHERE `id` = 'primary' AND `cash_balance` = 100000.00;
                    """)

                # Transactions Ledger Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS `transactions` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `trade_id` VARCHAR(50) UNIQUE NOT NULL,
                    `symbol` VARCHAR(20) NOT NULL,
                    `action` VARCHAR(10) NOT NULL,
                    `quantity` INT NOT NULL,
                    `price` DECIMAL(10,2) NOT NULL,
                    `gross_amount` DECIMAL(15,2) NOT NULL,
                    `broker_fee` DECIMAL(10,2) DEFAULT 0.00,
                    `sebon_fee` DECIMAL(10,2) DEFAULT 0.00,
                    `dp_charge` DECIMAL(10,2) DEFAULT 25.00,
                    `cgt_tax` DECIMAL(10,2) DEFAULT 0.00,
                    `net_amount` DECIMAL(15,2) NOT NULL,
                    `tms_order_no` VARCHAR(50) DEFAULT NULL,
                    `trade_type` VARCHAR(20) DEFAULT 'REAL',
                    `notes` TEXT,
                    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX `idx_symbol` (`symbol`),
                    INDEX `idx_created_at` (`created_at`)
                ) ENGINE=InnoDB;
                """)

                # Holdings Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS `holdings` (
                    `symbol` VARCHAR(20) PRIMARY KEY,
                    `quantity` INT NOT NULL,
                    `avg_buy_price` DECIMAL(10,2) NOT NULL,
                    `total_invested` DECIMAL(15,2) NOT NULL,
                    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB;
                """)

                # TMS & Broker Sync Config Table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS `system_settings` (
                    `key_name` VARCHAR(50) PRIMARY KEY,
                    `key_value` TEXT,
                    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB;
                """)

            conn.close()
            self.connected = True
            logger.info(f"✅ MySQL database '{self.config['database']}' initialized successfully")
        except Exception as e:
            self.connected = False
            logger.warning(f"MySQL connection unavailable: {e}")

    # ═══════════════════════════════════════
    #  FEE CALCULATIONS (Standard NEPSE)
    # ═══════════════════════════════════════
    @staticmethod
    def calculate_nepse_fees(action, gross_amount, profit=0.0):
        """
        Calculate NEPSE standard trading fees:
        - Broker commission: ~0.30%
        - SEBON fee: 0.015%
        - DP Charge: NPR 25
        - Capital Gains Tax (CGT): 5% (or 7.5%) on profit (SELL only)
        """
        # Broker fee tiers (simplified 0.30% standard)
        broker_fee = gross_amount * 0.0030
        sebon_fee = gross_amount * 0.00015
        dp_charge = 25.0

        cgt_tax = 0.0
        if action.upper() == 'SELL' and profit > 0:
            cgt_tax = profit * 0.05  # 5% capital gains tax

        if action.upper() == 'BUY':
            net_amount = gross_amount + broker_fee + sebon_fee + dp_charge
        else:
            net_amount = gross_amount - (broker_fee + sebon_fee + dp_charge + cgt_tax)

        return {
            'broker_fee': round(broker_fee, 2),
            'sebon_fee': round(sebon_fee, 2),
            'dp_charge': round(dp_charge, 2),
            'cgt_tax': round(cgt_tax, 2),
            'net_amount': round(net_amount, 2),
        }

    # ═══════════════════════════════════════
    #  TRANSACTION EXECUTION & LEDGER
    # ═══════════════════════════════════════
    def record_trade(self, symbol, action, quantity, price, tms_order_no=None, trade_type='REAL', notes=''):
        """Record trade in MySQL, update cash balance and holdings."""
        if not self.connected:
            return {'success': False, 'error': 'MySQL database is not connected'}

        action = action.upper()
        gross_amount = round(quantity * price, 2)
        trade_id = f"TRD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{symbol}"

        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                # Check current holding for SELL
                cur.execute("SELECT * FROM `holdings` WHERE `symbol` = %s;", (symbol,))
                existing_holding = cur.fetchone()

                profit = 0.0
                if action == 'SELL':
                    if not existing_holding or existing_holding['quantity'] < quantity:
                        return {'success': False, 'error': f"Insufficient shares to sell. You have {existing_holding['quantity'] if existing_holding else 0} shares of {symbol}."}
                    avg_price = float(existing_holding['avg_buy_price'])
                    profit = max(0.0, (price - avg_price) * quantity)

                # Calculate standard NEPSE broker fees & taxes
                fees = self.calculate_nepse_fees(action, gross_amount, profit)

                # Check account cash balance for BUY
                cur.execute("SELECT `cash_balance` FROM `accounts` WHERE `id` = 'primary';")
                acc = cur.fetchone()
                current_cash = float(acc['cash_balance']) if acc else 0.0

                if action == 'BUY' and current_cash < fees['net_amount']:
                    return {'success': False, 'error': f"Insufficient cash balance. Required NPR {fees['net_amount']:,.2f}, Available: NPR {current_cash:,.2f}"}

                # Insert into Transactions
                cur.execute("""
                INSERT INTO `transactions` 
                (`trade_id`, `symbol`, `action`, `quantity`, `price`, `gross_amount`, `broker_fee`, `sebon_fee`, `dp_charge`, `cgt_tax`, `net_amount`, `tms_order_no`, `trade_type`, `notes`, `created_at`)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    trade_id, symbol, action, quantity, price, gross_amount,
                    fees['broker_fee'], fees['sebon_fee'], fees['dp_charge'],
                    fees['cgt_tax'], fees['net_amount'], tms_order_no, trade_type, notes,
                    datetime.now()
                ))

                # Update Account Cash
                if action == 'BUY':
                    new_cash = current_cash - fees['net_amount']
                else:
                    new_cash = current_cash + fees['net_amount']

                cur.execute("UPDATE `accounts` SET `cash_balance` = %s WHERE `id` = 'primary';", (new_cash,))

                # Update Holdings
                if action == 'BUY':
                    if existing_holding:
                        old_qty = existing_holding['quantity']
                        old_invested = float(existing_holding['total_invested'])
                        new_qty = old_qty + quantity
                        new_invested = old_invested + gross_amount
                        new_avg_price = round(new_invested / new_qty, 2)
                        cur.execute("""
                        UPDATE `holdings` SET `quantity` = %s, `avg_buy_price` = %s, `total_invested` = %s WHERE `symbol` = %s;
                        """, (new_qty, new_avg_price, new_invested, symbol))
                    else:
                        cur.execute("""
                        INSERT INTO `holdings` (`symbol`, `quantity`, `avg_buy_price`, `total_invested`)
                        VALUES (%s, %s, %s, %s);
                        """, (symbol, quantity, price, gross_amount))
                elif action == 'SELL':
                    old_qty = existing_holding['quantity']
                    new_qty = old_qty - quantity
                    if new_qty <= 0:
                        cur.execute("DELETE FROM `holdings` WHERE `symbol` = %s;", (symbol,))
                    else:
                        avg_p = float(existing_holding['avg_buy_price'])
                        new_invested = round(new_qty * avg_p, 2)
                        cur.execute("""
                        UPDATE `holdings` SET `quantity` = %s, `total_invested` = %s WHERE `symbol` = %s;
                        """, (new_qty, new_invested, symbol))

            conn.close()
            return {
                'success': True,
                'trade': {
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': price,
                    'gross_amount': gross_amount,
                    'fees': fees,
                    'net_amount': fees['net_amount'],
                    'tms_order_no': tms_order_no,
                }
            }
        except Exception as e:
            logger.error(f"Error recording trade in MySQL: {e}")
            return {'success': False, 'error': str(e)}

    # ═══════════════════════════════════════
    #  PROFILE & LEDGER RETRIEVAL
    # ═══════════════════════════════════════
    def update_cash_balance(self, amount: float, is_deposit: bool = False) -> dict:
        """Update account cash balance or record a fund deposit."""
        if not self.connected:
            return {'success': False, 'error': 'Database not connected'}
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                if is_deposit:
                    cur.execute("""
                    UPDATE `accounts` 
                    SET `cash_balance` = `cash_balance` + %s,
                        `initial_fund` = `initial_fund` + %s
                    WHERE `id` = 'primary';
                    """, (amount, amount))
                else:
                    cur.execute("""
                    UPDATE `accounts` 
                    SET `cash_balance` = %s,
                        `initial_fund` = %s
                    WHERE `id` = 'primary';
                    """, (amount, amount))
                conn.commit()
            conn.close()
            return {'success': True, 'cash_balance': amount}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_account_profile(self, current_prices=None):
        """Fetch account overview, live portfolio valuation, and transaction ledger from MySQL."""
        if not self.connected:
            return {
                'connected': False,
                'config': self.config,
                'error': 'MySQL Database Not Connected. Please enter your MySQL credentials.'
            }

        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                # Account summary
                cur.execute("SELECT * FROM `accounts` WHERE `id` = 'primary';")
                account = cur.fetchone()

                # Holdings
                cur.execute("SELECT * FROM `holdings` ORDER BY `symbol` ASC;")
                holdings_raw = cur.fetchall()

                # Recent Transactions
                cur.execute("SELECT * FROM `transactions` ORDER BY `created_at` DESC LIMIT 100;")
                transactions = cur.fetchall()

                # Total fee statistics
                cur.execute("""
                SELECT 
                    SUM(`broker_fee`) AS total_broker_fee,
                    SUM(`sebon_fee`) AS total_sebon_fee,
                    SUM(`dp_charge`) AS total_dp_charge,
                    SUM(`cgt_tax`) AS total_cgt_tax,
                    COUNT(*) AS total_trades
                FROM `transactions`;
                """)
                fee_stats = cur.fetchone()

            conn.close()

            # Compute Live Valuation for Holdings
            current_prices = current_prices or {}
            holdings = []
            total_stock_value = 0.0
            total_invested = 0.0

            for h in holdings_raw:
                sym = h['symbol']
                qty = h['quantity']
                avg_p = float(h['avg_buy_price'])
                invested = float(h['total_invested'])
                market_p = float(current_prices.get(sym, avg_p))
                curr_val = round(qty * market_p, 2)
                pnl = round(curr_val - invested, 2)
                pnl_pct = round((pnl / invested) * 100, 2) if invested > 0 else 0.0

                total_stock_value += curr_val
                total_invested += invested

                holdings.append({
                    'symbol': sym,
                    'quantity': qty,
                    'avg_buy_price': avg_p,
                    'total_invested': invested,
                    'current_price': market_p,
                    'current_value': curr_val,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                })

            cash_balance = float(account['cash_balance']) if account else 0.0
            initial_fund = float(account['initial_fund']) if account else 0.0
            total_portfolio_val = cash_balance + total_stock_value
            overall_pnl = total_portfolio_val - initial_fund
            overall_pnl_pct = (overall_pnl / initial_fund) * 100 if initial_fund > 0 else 0.0

            # Format transactions for JSON
            tx_list = []
            for tx in transactions:
                tx_list.append({
                    'id': tx['id'],
                    'trade_id': tx['trade_id'],
                    'symbol': tx['symbol'],
                    'action': tx['action'],
                    'quantity': tx['quantity'],
                    'price': float(tx['price']),
                    'gross_amount': float(tx['gross_amount']),
                    'broker_fee': float(tx['broker_fee']),
                    'sebon_fee': float(tx['sebon_fee']),
                    'dp_charge': float(tx['dp_charge']),
                    'cgt_tax': float(tx['cgt_tax']),
                    'net_amount': float(tx['net_amount']),
                    'tms_order_no': tx['tms_order_no'] or '—',
                    'trade_type': tx['trade_type'],
                    'notes': tx['notes'] or '',
                    'timestamp': tx['created_at'].strftime('%Y-%m-%d %H:%M:%S') if tx['created_at'] else ''
                })

            return {
                'connected': True,
                'config': {
                    'host': self.config['host'],
                    'port': self.config['port'],
                    'user': self.config['user'],
                    'database': self.config['database'],
                },
                'account': {
                    'name': account['name'] if account else 'Main Account',
                    'broker_id': account['broker_id'] if account else 'TMS-29',
                    'client_code': account['client_code'] if account else 'CLIENT-001',
                    'cash_balance': cash_balance,
                    'initial_fund': initial_fund,
                    'total_stock_value': round(total_stock_value, 2),
                    'total_portfolio_value': round(total_portfolio_val, 2),
                    'overall_pnl': round(overall_pnl, 2),
                    'overall_pnl_pct': round(overall_pnl_pct, 2),
                },
                'holdings': holdings,
                'transactions': tx_list,
                'fees_summary': {
                    'total_broker_fee': float(fee_stats['total_broker_fee'] or 0),
                    'total_sebon_fee': float(fee_stats['total_sebon_fee'] or 0),
                    'total_dp_charge': float(fee_stats['total_dp_charge'] or 0),
                    'total_cgt_tax': float(fee_stats['total_cgt_tax'] or 0),
                    'total_trades': int(fee_stats['total_trades'] or 0),
                }
            }

        except Exception as e:
            logger.error(f"Error fetching account profile from MySQL: {e}")
            return {
                'connected': False,
                'config': self.config,
                'error': str(e)
            }


# Singleton instance
db_manager = DatabaseManager()
