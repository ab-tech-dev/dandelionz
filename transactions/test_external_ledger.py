"""
Card money in the finance ledger: payments in, refunds out, and the guarantees around them.

Card payments move no wallet, so they are written as EXTERNAL-bucket rows that never change a
balance (see transactions/external_ledger.py).
"""

import csv
import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from transactions import ledger_report
from transactions.management.commands.reconcile_wallets import all_ledger_totals
from transactions.models import (
    DeliveryCharge, InstallmentCharge, InstallmentPayment, InstallmentPlan, LedgerEntry,
    Order, OrderPaymentRefund, Payment, Wallet,
)
from users.models import Customer

User = get_user_model()
Type = LedgerEntry.EntryType
Bucket = LedgerEntry.Bucket


def external():
    return LedgerEntry.objects.filter(bucket=Bucket.EXTERNAL)


class Base(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email='card@test.com', password='pass12345', role='CUSTOMER', full_name='Card Payer',
        )
        Customer.objects.get_or_create(user=self.customer)
        self.wallet, _ = Wallet.objects.get_or_create(user=self.customer)

    def order(self, total='5000.00', status=Order.Status.PENDING):
        return Order.objects.create(
            customer=self.customer, total_price=Decimal(total),
            status=status, payment_status='UNPAID',
        )

    def plan(self, total=Decimal('6000.00'), n=3):
        order = self.order(total=str(total))
        base = (total / n).quantize(Decimal('0.01'), rounding='ROUND_DOWN')
        plan = InstallmentPlan.objects.create(
            order=order, duration='3_months', total_amount=total,
            installment_amount=base, number_of_installments=n, status='ACTIVE',
        )
        for i in range(1, n + 1):
            InstallmentPayment.objects.create(
                installment_plan=plan, payment_number=i, amount=base,
                due_date=timezone.now() + timedelta(days=30 * i),
                reference=f"{order.order_id}-inst-{i}",
            )
        return plan


class OrderCardPaymentTests(Base):
    def test_card_leg_is_recorded_as_external_credit(self):
        order = self.order('5000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('5000.00'), reference='ORD-A-1')
        payment.mark_as_successful()

        row = external().get()
        self.assertEqual(row.entry_type, Type.CARD_ORDER_PAYMENT)
        self.assertEqual(row.direction, LedgerEntry.Direction.CREDIT)
        self.assertEqual(row.amount, Decimal('5000.00'))
        self.assertEqual(row.reference, 'ORD-A-1')
        self.assertEqual(row.balance_after, Decimal('0.00'))
        self.assertEqual(row.wallet, self.wallet)
        self.assertEqual(row.order, order)
        self.assertEqual(row.payment, payment)

    def test_wallet_balances_are_untouched(self):
        order = self.order('5000.00')
        Payment.objects.create(order=order, amount=Decimal('5000.00'), reference='ORD-A-2').mark_as_successful()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('0.00'))
        self.assertEqual(self.wallet.balance, Decimal('0.00'))

    def test_settling_twice_writes_one_row(self):
        order = self.order('5000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('5000.00'), reference='ORD-A-3')
        payment.mark_as_successful()
        payment.mark_as_successful()
        self.assertEqual(external().count(), 1)

    def test_fully_wallet_funded_order_writes_nothing(self):
        # A wallet-only checkout has a zero card leg.
        order = self.order('5000.00')
        Payment.objects.create(order=order, amount=Decimal('0.00'), reference='ORD-A-4').mark_as_successful()
        self.assertEqual(external().count(), 0)

    def test_a_ledger_failure_never_fails_the_payment(self):
        order = self.order('5000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('5000.00'), reference='ORD-A-5')
        with patch('transactions.external_ledger.LedgerEntry.objects.get_or_create',
                   side_effect=RuntimeError('db hiccup')):
            payment.mark_as_successful()
        payment.refresh_from_db()
        self.assertTrue(payment.verified)
        self.assertEqual(payment.status, 'SUCCESS')
        self.assertEqual(external().count(), 0)


class InstallmentCardPaymentTests(Base):
    def _settle_card_charge(self, plan, amount='1000.00', reference='INS-1-abc'):
        charge = InstallmentCharge.objects.create(
            plan=plan, reference=reference, amount=Decimal(amount),
            method=InstallmentCharge.Method.CARD,
        )
        from transactions import installment_payment as inst
        inst.settle_installment_charge(charge)
        return charge

    def test_card_installment_is_recorded(self):
        plan = self.plan()
        self._settle_card_charge(plan)
        row = external().get()
        self.assertEqual(row.entry_type, Type.CARD_INSTALLMENT_PAYMENT)
        self.assertEqual(row.direction, LedgerEntry.Direction.CREDIT)
        self.assertEqual(row.amount, Decimal('1000.00'))
        self.assertEqual(row.order, plan.order)
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('1000.00'))

    def test_settling_the_same_charge_twice_writes_one_row(self):
        plan = self.plan()
        charge = self._settle_card_charge(plan)
        from transactions import installment_payment as inst
        inst.settle_installment_charge(charge)
        self.assertEqual(external().count(), 1)
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('1000.00'))

    def test_wallet_installment_is_not_duplicated_as_external(self):
        plan = self.plan()
        self.wallet.credit(Decimal('3000'), source='t', bucket=Bucket.SPENDABLE, entry_type=Type.DEPOSIT)
        from transactions import installment_payment as inst
        inst.initialize_installment_payment(plan, callback_url='https://x.test', amount='1000', use_wallet=True)
        self.assertEqual(external().count(), 0)
        self.assertEqual(
            LedgerEntry.objects.filter(entry_type=Type.ORDER_PAYMENT).count(), 1,
        )

    @patch('transactions.installment_payment.Paystack')
    def test_stranded_installment_records_money_in_and_back_out(self, Paystack):
        Paystack.return_value.refund.return_value = {'data': {'id': 77}}
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-1-old', amount=Decimal('1500.00'),
            method=InstallmentCharge.Method.CARD, status=InstallmentCharge.Status.CANCELLED,
        )
        from transactions import installment_payment as inst
        inst._refund_stranded_installment(charge, {'amount': 150000, 'id': 5}, 'link replaced')
        inst._refund_stranded_installment(charge, {'amount': 150000, 'id': 5}, 'link replaced')

        rows = {r.direction: r for r in external()}
        self.assertEqual(external().count(), 2)
        self.assertEqual(rows['CREDIT'].entry_type, Type.CARD_INSTALLMENT_PAYMENT)
        self.assertEqual(rows['DEBIT'].entry_type, Type.CARD_REFUND)
        self.assertEqual(rows['CREDIT'].amount, rows['DEBIT'].amount)
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('0.00'))


class DeliveryCardPaymentTests(Base):
    def _charge(self, card, wallet=Decimal('0.00'), ref='DLV-1'):
        order = self.order('5000.00', status=Order.Status.PAID)
        return DeliveryCharge.objects.create(
            order=order, reference=ref, amount=card + wallet,
            card_amount=card, wallet_amount=wallet,
        )

    def test_card_leg_of_delivery_fee_is_recorded(self):
        from transactions import delivery_payment
        delivery_payment.settle_delivery_charge(self._charge(Decimal('800.00')))
        row = external().get()
        self.assertEqual(row.entry_type, Type.CARD_DELIVERY_FEE)
        self.assertEqual(row.amount, Decimal('800.00'))

    def test_settling_twice_writes_one_row(self):
        from transactions import delivery_payment
        charge = self._charge(Decimal('800.00'), ref='DLV-2')
        delivery_payment.settle_delivery_charge(charge)
        delivery_payment.settle_delivery_charge(charge)
        self.assertEqual(external().count(), 1)

    @patch('transactions.delivery_payment.Paystack')
    def test_stranded_delivery_records_money_in_and_back_out(self, Paystack):
        Paystack.return_value.refund.return_value = {'data': {'id': 9}}
        from transactions import delivery_payment
        charge = self._charge(Decimal('600.00'), ref='DLV-3')
        charge.status = DeliveryCharge.Status.CANCELLED
        charge.save()
        delivery_payment._refund_stranded_delivery(charge, {'amount': 60000, 'id': 3}, 'replaced')
        self.assertEqual(
            sorted(external().values_list('entry_type', 'direction')),
            sorted([(Type.CARD_DELIVERY_FEE, 'CREDIT'), (Type.CARD_REFUND, 'DEBIT')]),
        )


class OrderPaymentRefundTests(Base):
    def test_processed_refund_records_both_sides_once(self):
        order = self.order('4000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('4000.00'), reference='ORD-R-1')
        refund = OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='RFD-1', amount=Decimal('4000.00'), reason='stranded',
        )
        self.assertEqual(external().count(), 0)  # nothing until Paystack settles it

        refund.mark_as_processed('55')
        refund.mark_as_processed('55')

        self.assertEqual(external().count(), 2)
        self.assertEqual(external().filter(direction='CREDIT').get().entry_type, Type.CARD_ORDER_PAYMENT)
        self.assertEqual(external().filter(direction='DEBIT').get().entry_type, Type.CARD_REFUND)

    def test_failed_refund_records_nothing(self):
        order = self.order('4000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('4000.00'), reference='ORD-R-2')
        refund = OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='RFD-2', amount=Decimal('4000.00'),
        )
        refund.mark_as_failed('declined')
        self.assertEqual(external().count(), 0)


class ReportAndReconcileTests(Base):
    def _seed(self):
        self.wallet.credit(Decimal('2000'), source='t', bucket=Bucket.SPENDABLE, entry_type=Type.DEPOSIT)
        order = self.order('5000.00')
        Payment.objects.create(order=order, amount=Decimal('5000.00'), reference='ORD-S-1').mark_as_successful()
        order2 = self.order('1000.00')
        pay2 = Payment.objects.create(order=order2, amount=Decimal('1000.00'), reference='ORD-S-2')
        OrderPaymentRefund.objects.create(
            payment=pay2, order=order2, reference='RFD-S', amount=Decimal('1000.00'),
        ).mark_as_processed()

    def test_summary_totals_include_everything_and_isolate_external(self):
        self._seed()
        s = ledger_report.summarise(LedgerEntry.objects.all())
        # Credits: 2000 deposit + 5000 card order + 1000 stranded card-in. Debits: 1000 refund.
        self.assertEqual(s['total_credits'], '8000.00')
        self.assertEqual(s['total_debits'], '1000.00')
        self.assertEqual(s['external_in'], '6000.00')
        self.assertEqual(s['external_out'], '1000.00')
        self.assertEqual(s['external_net'], '5000.00')
        self.assertEqual(s['external_count'], 3)

    def test_summary_external_fields_are_zero_with_no_card_money(self):
        self.wallet.credit(Decimal('500'), source='t', bucket=Bucket.SPENDABLE, entry_type=Type.DEPOSIT)
        s = ledger_report.summarise(LedgerEntry.objects.all())
        self.assertEqual((s['external_in'], s['external_out'], s['external_count']), ('0.00', '0.00', 0))

    def test_bucket_and_type_filters_find_card_rows(self):
        self._seed()
        by_bucket = ledger_report.filtered_entries({'bucket': 'EXTERNAL'})
        self.assertEqual(by_bucket.count(), 3)
        by_type = ledger_report.filtered_entries({'entry_type': 'CARD_REFUND'})
        self.assertEqual(by_type.count(), 1)

    def test_csv_export_blanks_balance_after_for_card_rows(self):
        self._seed()
        response = ledger_report.export_csv(LedgerEntry.objects.all(), 'ledger')
        rows = list(csv.DictReader(io.StringIO(b''.join(response.streaming_content).decode())))
        card = [r for r in rows if r['Bucket'] == 'EXTERNAL']
        self.assertEqual(len(card), 3)
        self.assertTrue(all(r['Balance After (NGN)'] == '' for r in card))
        wallet_rows = [r for r in rows if r['Bucket'] != 'EXTERNAL']
        self.assertTrue(all(r['Balance After (NGN)'] != '' for r in wallet_rows))

    def test_xlsx_export_survives_card_rows(self):
        self._seed()
        response = ledger_report.export_xlsx(LedgerEntry.objects.all(), 'ledger')
        self.assertEqual(response.status_code, 200)

    def test_reconcile_ignores_external_rows(self):
        self._seed()
        totals = all_ledger_totals()
        self.assertEqual(totals[self.wallet.pk][Bucket.SPENDABLE], Decimal('2000.00'))
        self.assertNotIn(Bucket.EXTERNAL, totals[self.wallet.pk])
        call_command('reconcile_wallets', stdout=io.StringIO())

    def _admin_client(self):
        admin = User.objects.create_user(
            email='adm@test.com', password='pass12345', role='ADMIN', full_name='Adm',
        )
        client = APIClient()
        client.force_authenticate(user=admin)
        return client

    def test_admin_ledger_api_lists_card_rows_with_their_owner(self):
        self._seed()
        response = self._admin_client().get(reverse('admin-ledger'), {'bucket': 'EXTERNAL'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body.get('results') or body.get('data', {}).get('results') or body.get('data')
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row['bucket'], 'EXTERNAL')
            self.assertEqual(row['user_email'], 'card@test.com')
            self.assertTrue(row['entry_type'].startswith('CARD_'))
            self.assertEqual(row['balance_after'], '0.00')

    def test_admin_summary_api_exposes_external_totals(self):
        self._seed()
        response = self._admin_client().get(reverse('admin-ledger-summary'))
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['total_credits'], '8000.00')
        self.assertEqual(data['total_debits'], '1000.00')
        self.assertEqual(data['external_in'], '6000.00')
        self.assertEqual(data['external_out'], '1000.00')
        # The existing keys the apps already read are all still present.
        for key in ('count', 'net', 'by_type', 'by_bucket', 'filters'):
            self.assertIn(key, data)


class BackfillCardLedgerTests(Base):
    def _legacy_card_history(self):
        """Card money recorded by the old code: settled rows with no ledger entries."""
        order = self.order('5000.00', status=Order.Status.PAID)
        Payment.objects.create(
            order=order, amount=Decimal('5000.00'), reference='ORD-L-1',
            status='SUCCESS', verified=True, paid_at=timezone.now() - timedelta(days=3),
        )
        # An installment plan's own Payment row is a record, not a card charge: must be skipped.
        plan = self.plan(Decimal('3000.00'), 3)
        Payment.objects.create(
            order=plan.order, amount=Decimal('3000.00'), reference='ORD-L-PLAN',
            status='SUCCESS', verified=True, paid_at=timezone.now(),
        )
        InstallmentCharge.objects.create(
            plan=plan, reference='INS-L-1', amount=Decimal('1000.00'),
            method=InstallmentCharge.Method.CARD, status=InstallmentCharge.Status.PAID,
            paid_at=timezone.now() - timedelta(days=2),
        )
        InstallmentCharge.objects.create(
            plan=plan, reference='INS-L-WAL', amount=Decimal('500.00'),
            method=InstallmentCharge.Method.WALLET, status=InstallmentCharge.Status.PAID,
        )
        DeliveryCharge.objects.create(
            order=order, reference='DLV-L-1', amount=Decimal('700.00'),
            card_amount=Decimal('700.00'), status=DeliveryCharge.Status.PAID,
            paid_at=timezone.now() - timedelta(days=1),
        )

    def _run(self, *args):
        out = io.StringIO()
        call_command('backfill_card_ledger', *args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_dry_run_reports_without_writing(self):
        self._legacy_card_history()
        before = LedgerEntry.objects.count()
        output = self._run('--dry-run')
        self.assertEqual(LedgerEntry.objects.count(), before)
        self.assertIn('Would write', output)

    def test_backfill_writes_card_rows_only_and_is_idempotent(self):
        self._legacy_card_history()
        # Opening row so there is a "ledger start" to clamp against.
        self.wallet.credit(Decimal('100'), source='t', bucket=Bucket.SPENDABLE, entry_type=Type.DEPOSIT)

        self._run()
        types = sorted(external().values_list('entry_type', flat=True))
        self.assertEqual(types, sorted([
            Type.CARD_ORDER_PAYMENT, Type.CARD_INSTALLMENT_PAYMENT, Type.CARD_DELIVERY_FEE,
        ]))
        self.assertEqual(sum(r.amount for r in external()), Decimal('6700.00'))

        second = self._run()
        self.assertEqual(external().count(), 3)
        self.assertIn('Nothing to write', second)

    def test_backfilled_rows_are_never_dated_before_the_ledger_started(self):
        self._legacy_card_history()
        self.wallet.credit(Decimal('100'), source='t', bucket=Bucket.SPENDABLE, entry_type=Type.DEPOSIT)
        start = LedgerEntry.objects.order_by('created_at').first().created_at
        self._run()
        self.assertTrue(all(r.created_at >= start for r in external()))
        # The boundary the payout-retry check relies on has not moved.
        self.assertEqual(LedgerEntry.objects.order_by('created_at').first().created_at, start)

    def test_backfill_does_not_duplicate_rows_the_live_hooks_wrote(self):
        order = self.order('5000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('5000.00'), reference='ORD-L-2')
        payment.mark_as_successful()  # live hook writes the row
        self._run()
        self.assertEqual(external().count(), 1)

    def test_backfill_includes_processed_order_refunds(self):
        order = self.order('4000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('4000.00'), reference='ORD-L-3')
        refund = OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='RFD-L-3', amount=Decimal('4000.00'),
            status=OrderPaymentRefund.Status.PROCESSED, settled_at=timezone.now(),
        )
        self._run()
        self.assertEqual(
            sorted(external().values_list('direction', flat=True)), ['CREDIT', 'DEBIT'],
        )


class AdminPaymentAlertTests(Base):
    """Admins get a push/in-app alert for money movements, exactly once per payment."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        patcher = patch('transactions.tasks.notify_admin')
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def _titles(self):
        return [c.args[0] for c in self.notify.call_args_list]

    def test_installment_payment_alerts_admins_with_push_and_no_email(self):
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-A-1', amount=Decimal('1000.00'),
            method=InstallmentCharge.Method.CARD,
        )
        from transactions import installment_payment as inst
        with self.captureOnCommitCallbacks(execute=True):
            inst.settle_installment_charge(charge)

        self.assertEqual(self._titles(), ["Installment payment received"])
        call = self.notify.call_args
        self.assertIn('₦1,000.00', call.args[1])
        self.assertIn('card@test.com', call.args[1])
        self.assertTrue(call.kwargs['send_push'])
        self.assertFalse(call.kwargs['send_email'])
        self.assertEqual(call.kwargs['reference'], 'INS-A-1')

    def test_wallet_installment_also_alerts(self):
        plan = self.plan()
        self.wallet.credit(Decimal('3000'), source='t', bucket=Bucket.SPENDABLE, entry_type=Type.DEPOSIT)
        from transactions import installment_payment as inst
        with self.captureOnCommitCallbacks(execute=True):
            inst.initialize_installment_payment(plan, callback_url='https://x.test', amount='1000', use_wallet=True)
        self.assertEqual(self._titles(), ["Installment payment received"])

    def test_settling_the_same_payment_twice_alerts_once(self):
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-A-2', amount=Decimal('1000.00'),
            method=InstallmentCharge.Method.CARD,
        )
        from transactions import admin_alerts, installment_payment as inst
        with self.captureOnCommitCallbacks(execute=True):
            inst.settle_installment_charge(charge)
        # Simulate the racing second settler getting past the status check as well.
        with self.captureOnCommitCallbacks(execute=True):
            admin_alerts.alert_admins(
                title="Installment payment received", message='dup',
                dedupe_key='installment-INS-A-2',
            )
        self.assertEqual(len(self.notify.call_args_list), 1)

    def test_no_alert_until_the_transaction_commits(self):
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-A-3', amount=Decimal('1000.00'),
            method=InstallmentCharge.Method.CARD,
        )
        from transactions import installment_payment as inst
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            inst.settle_installment_charge(charge)
        self.assertEqual(self.notify.call_count, 0)
        self.assertTrue(callbacks)

    def test_delivery_fee_alerts(self):
        order = self.order('5000.00', status=Order.Status.PAID)
        charge = DeliveryCharge.objects.create(
            order=order, reference='DLV-A-1', amount=Decimal('800.00'),
            card_amount=Decimal('800.00'), wallet_amount=Decimal('0.00'),
        )
        from transactions import delivery_payment
        with self.captureOnCommitCallbacks(execute=True):
            delivery_payment.settle_delivery_charge(charge)
        self.assertEqual(self._titles(), ["Delivery fee paid"])
        self.assertIn('₦800.00', self.notify.call_args.args[1])
        self.assertIn('DLV-A-1', self.notify.call_args.args[1])

    def test_wallet_topup_alerts_once(self):
        from transactions.models import WalletDeposit
        deposit = WalletDeposit.objects.create(
            user=self.customer, amount=Decimal('2000.00'), reference='DEP-A-1',
        )
        with self.captureOnCommitCallbacks(execute=True):
            deposit.mark_as_successful()
            deposit.mark_as_successful()
        self.assertEqual(self._titles(), ["Wallet top-up received"])

    def test_card_refund_alerts(self):
        order = self.order('4000.00')
        payment = Payment.objects.create(order=order, amount=Decimal('4000.00'), reference='ORD-A-R')
        refund = OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='RFD-A-1', amount=Decimal('4000.00'),
            reason='stranded',
        )
        with self.captureOnCommitCallbacks(execute=True):
            refund.mark_as_processed('1')
            refund.mark_as_processed('1')
        self.assertEqual(self._titles(), ["Card refund processed"])

    @patch('transactions.installment_payment.Paystack')
    def test_stranded_installment_refund_alerts(self, Paystack):
        Paystack.return_value.refund.return_value = {'data': {'id': 7}}
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-A-S', amount=Decimal('1500.00'),
            method=InstallmentCharge.Method.CARD, status=InstallmentCharge.Status.CANCELLED,
        )
        from transactions import installment_payment as inst
        with self.captureOnCommitCallbacks(execute=True):
            inst._refund_stranded_installment(charge, {'amount': 150000, 'id': 5}, 'link replaced')
        self.assertEqual(self._titles(), ["Payment returned to card"])

    def test_a_failing_alert_never_fails_the_payment(self):
        self.notify.side_effect = RuntimeError('push provider down')
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-A-F', amount=Decimal('1000.00'),
            method=InstallmentCharge.Method.CARD,
        )
        from transactions import installment_payment as inst
        with self.captureOnCommitCallbacks(execute=True):
            inst.settle_installment_charge(charge)
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('1000.00'))


class AdminAlertEndToEndTests(Base):
    """
    The real notification pipeline, with no mock on notify_admin: an admin gets a stored
    notification and a push for an installment payment; a customer and a suspended admin do not.
    """

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        self.admin = User.objects.create_user(
            email='admin1@test.com', password='pass12345', role='ADMIN', full_name='Admin One',
        )
        self.other_customer = User.objects.create_user(
            email='other@test.com', password='pass12345', role='CUSTOMER', full_name='Other',
        )
        self.suspended = User.objects.create_user(
            email='admin2@test.com', password='pass12345', role='ADMIN', full_name='Suspended',
        )
        User.objects.filter(pk=self.suspended.pk).update(is_active=False)

        from users.notification_service import NotificationService
        self.push = patch.object(NotificationService, 'send_push_notification', return_value=True)
        self.socket = patch.object(NotificationService, 'send_websocket_notification', return_value=True)
        self.email = patch.object(NotificationService, 'send_email_notification', return_value=True)
        self.push_mock = self.push.start()
        self.socket_mock = self.socket.start()
        self.email_mock = self.email.start()
        for p in (self.push, self.socket, self.email):
            self.addCleanup(p.stop)

    def test_admin_receives_a_stored_notification_and_a_push_but_no_email(self):
        from users.notification_models import Notification
        plan = self.plan()
        charge = InstallmentCharge.objects.create(
            plan=plan, reference='INS-E2E-1', amount=Decimal('2000.00'),
            method=InstallmentCharge.Method.CARD,
        )
        from transactions import installment_payment as inst
        with self.captureOnCommitCallbacks(execute=True):
            inst.settle_installment_charge(charge)

        mine = Notification.objects.filter(user=self.admin, title="Installment payment received")
        self.assertEqual(mine.count(), 1)
        note = mine.get()
        self.assertIn('₦2,000.00', note.message)
        self.assertEqual(note.metadata['reference'], 'INS-E2E-1')
        self.assertEqual(note.metadata['amount'], '2000.00')

        self.assertTrue(self.push_mock.called)
        self.assertTrue(self.socket_mock.called)
        self.assertFalse(self.email_mock.called)

        # Not the paying customer, another customer, or a deactivated admin.
        for user in (self.customer, self.other_customer, self.suspended):
            self.assertFalse(
                Notification.objects.filter(user=user, title="Installment payment received").exists(),
                f"{user.email} should not be alerted",
            )


class ThroughTheRealWebhookTests(Base):
    """The ledger rows are reached by the actual Paystack webhook, not just by direct calls."""

    SECRET = 'sk_test_dummy_secret'

    def setUp(self):
        super().setUp()
        patcher = patch('transactions.tasks.notify_stakeholders_order_paid.delay')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, payload):
        import hashlib
        import hmac
        import json
        from django.test import override_settings
        body = json.dumps(payload).encode()
        sig = hmac.new(self.SECRET.encode(), body, hashlib.sha512).hexdigest()
        with override_settings(PAYSTACK_SECRET_KEY=self.SECRET):
            return self.client.post(
                '/transactions/webhook/', data=body, content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

    @patch('transactions.views.Paystack.verify_payment')
    def test_card_order_payment_webhook_writes_one_ledger_row(self, verify):
        order = self.order('1000.00')
        Payment.objects.create(order=order, amount=Decimal('1000.00'), reference='ORD-WH-1')
        verify.return_value = {'data': {'status': 'success', 'currency': 'NGN', 'amount': 100000}}

        self._post({'id': 1, 'event': 'charge.success', 'data': {'reference': 'ORD-WH-1'}})
        self._post({'id': 1, 'event': 'charge.success', 'data': {'reference': 'ORD-WH-1'}})  # retry
        self._post({'id': 2, 'event': 'charge.success', 'data': {'reference': 'ORD-WH-1'}})  # new event

        row = external().get()
        self.assertEqual(row.entry_type, Type.CARD_ORDER_PAYMENT)
        self.assertEqual(row.amount, Decimal('1000.00'))
        self.assertEqual(row.reference, 'ORD-WH-1')

    def test_refund_processed_webhook_writes_card_in_and_out(self):
        order = self.order('2500.00')
        payment = Payment.objects.create(order=order, amount=Decimal('2500.00'), reference='ORD-WH-2')
        OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='RFD-WH-2', amount=Decimal('2500.00'),
            status=OrderPaymentRefund.Status.PROCESSING,
        )
        response = self._post({
            'id': 3, 'event': 'refund.processed',
            'data': {'id': 9001, 'transaction_reference': 'ORD-WH-2'},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(external().values_list('entry_type', 'direction', 'amount')),
            sorted([
                (Type.CARD_ORDER_PAYMENT, 'CREDIT', Decimal('2500.00')),
                (Type.CARD_REFUND, 'DEBIT', Decimal('2500.00')),
            ]),
        )

    def test_refund_failed_webhook_writes_nothing(self):
        order = self.order('2500.00')
        payment = Payment.objects.create(order=order, amount=Decimal('2500.00'), reference='ORD-WH-3')
        OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='RFD-WH-3', amount=Decimal('2500.00'),
            status=OrderPaymentRefund.Status.PROCESSING,
        )
        self._post({
            'id': 4, 'event': 'refund.failed',
            'data': {'id': 9002, 'transaction_reference': 'ORD-WH-3', 'message': 'declined'},
        })
        self.assertEqual(external().count(), 0)


class MoreAlertCoverageTests(Base):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()
        patcher = patch('transactions.tasks.notify_admin')
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def test_deposit_refund_processed_alerts_once(self):
        from transactions.models import DepositRefund, WalletDeposit
        deposit = WalletDeposit.objects.create(
            user=self.customer, amount=Decimal('3000.00'), reference='DEP-MA-1',
            status='SUCCESS', verified=True,
        )
        refund = DepositRefund.objects.create(
            user=self.customer, deposit=deposit, reference='RFD-MA-1', amount=Decimal('3000.00'),
            status=DepositRefund.Status.PROCESSING,
        )
        with self.captureOnCommitCallbacks(execute=True):
            refund.mark_as_processed('77')
            refund.mark_as_processed('77')
        self.assertEqual([c.args[0] for c in self.notify.call_args_list], ["Deposit refund processed"])
        # Money already left the wallet as a normal ledger row when the refund was requested;
        # no card row is written for it.
        self.assertEqual(external().count(), 0)

    def test_the_celery_task_itself_runs_and_forwards_everything(self):
        from transactions.tasks import send_admin_payment_alert
        self.assertEqual(send_admin_payment_alert.name, 'transactions.send_admin_payment_alert')
        result = send_admin_payment_alert.apply(kwargs={
            'title': 'T', 'message': 'M', 'dedupe_key': 'task-test-1', 'kind': 'deposit',
            'amount': '10.00', 'reference': 'R1',
        })
        self.assertTrue(result.successful())
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.kwargs['reference'], 'R1')
        # The same payment's alert is not sent twice, even if the task is delivered twice.
        send_admin_payment_alert.apply(kwargs={
            'title': 'T', 'message': 'M', 'dedupe_key': 'task-test-1', 'kind': 'deposit',
        })
        self.assertEqual(self.notify.call_count, 1)

    def test_backfill_on_an_empty_database_is_a_clean_no_op(self):
        out = io.StringIO()
        call_command('backfill_card_ledger', '--dry-run', stdout=out)
        call_command('backfill_card_ledger', stdout=out)
        self.assertIn('Nothing to write', out.getvalue())
        self.assertEqual(LedgerEntry.objects.count(), 0)
