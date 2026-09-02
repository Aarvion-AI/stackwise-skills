# Subscription and Recurring Billing

## Stripe Subscriptions: Overview

Subscriptions automate recurring charges on a schedule. Key objects:

- **Customer** - Represents a person or account
- **Price** - Amount, currency, and billing interval
- **Subscription** - Ties a customer to a price with a billing schedule

## Creating a Subscription

### 1. Create or Retrieve Customer

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

async function createOrUpdateCustomer(customerId, email, name) {
  // Try to retrieve existing customer
  let customer;
  try {
    customer = await stripe.customers.retrieve(customerId);
  } catch (error) {
    // Customer doesn't exist, create new one
    customer = await stripe.customers.create({
      id: customerId, // Your internal ID
      email,
      name,
      metadata: {
        userId: customerId,
        signupDate: new Date().toISOString(),
      },
    });
  }
  return customer;
}
```

### 2. Create Price (Product + Billing Interval)

In Stripe Dashboard or via API:

```javascript
// Create a product once
const product = await stripe.products.create({
  name: 'Premium Subscription',
  description: 'Access to premium features',
  type: 'service',
});

// Create price (recurring)
const price = await stripe.prices.create({
  product: product.id,
  unit_amount: 9900, // $99.00 in cents
  currency: 'usd',
  recurring: {
    interval: 'month', // 'month', 'year', 'week', 'day'
    interval_count: 1, // Bill every 1 month
    aggregate_usage: 'sum', // For metered billing
  },
  metadata: {
    tier: 'premium',
  },
});
```

### 3. Create Subscription

```javascript
async function createSubscription(customerId, priceId) {
  const subscription = await stripe.subscriptions.create({
    customer: customerId,
    items: [
      {
        price: priceId,
        quantity: 1, // Can vary for per-user billing
      },
    ],
    payment_behavior: 'default_incomplete', // Require payment method
    expand: ['latest_invoice.payment_intent'], // Get invoice details
  });

  return subscription;
}
```

### 4. Collect Payment Method

For subscriptions that haven't been paid yet, collect a card:

```javascript
// Server-side
async function attachPaymentMethodToSubscription(subscriptionId, paymentMethodId) {
  const subscription = await stripe.subscriptions.update(subscriptionId, {
    default_payment_method: paymentMethodId,
  });

  // Confirm the payment if the latest invoice is pending
  if (subscription.latest_invoice) {
    const invoice = await stripe.invoices.retrieve(subscription.latest_invoice);
    if (invoice.status === 'open') {
      // Invoice still needs payment
      return { status: 'requires_payment', clientSecret: invoice.payment_intent.client_secret };
    }
  }

  return { status: 'active', subscription };
}
```

## Subscription Lifecycle

```
TRIALING ──> ACTIVE ──> PAST_DUE ──> UNPAID ──> CANCELED
                          ↓
                        (retry)
                          ↓
                        ACTIVE or CANCELED
```

### Handling Status Changes

```javascript
async function handleSubscriptionUpdated(subscription) {
  const { id, customer, status, current_period_end, items } = subscription;

  switch (status) {
    case 'active':
      // Subscription is active, customer has access
      await db.subscriptions.update(
        { stripeSubscriptionId: id },
        {
          status: 'active',
          renewsAt: new Date(current_period_end * 1000),
          features: ['premium_content', 'priority_support'],
        }
      );
      // Send welcome email
      await emailService.sendSubscriptionConfirmed(customer);
      break;

    case 'past_due':
      // Payment failed, retry scheduled
      console.warn(`Subscription past_due: ${id}`);
      // Don't revoke access yet - Stripe will retry
      break;

    case 'unpaid':
      // Multiple retries failed, subscription is in limbo
      // Revoke premium features but keep customer account
      await db.subscriptions.update(
        { stripeSubscriptionId: id },
        { status: 'unpaid', features: [] }
      );
      await emailService.sendPaymentFailedEmail(customer);
      break;

    case 'canceled':
      // Subscription ended
      await db.subscriptions.update(
        { stripeSubscriptionId: id },
        { status: 'canceled', canceledAt: new Date() }
      );
      await emailService.sendSubscriptionCanceledEmail(customer);
      break;
  }
}
```

## Canceling Subscriptions

### Immediate Cancellation

```javascript
async function cancelSubscription(subscriptionId) {
  const subscription = await stripe.subscriptions.del(subscriptionId);
  console.log(`Subscription canceled immediately: ${subscriptionId}`);
  return subscription;
}
```

### End-of-Billing-Period Cancellation

```javascript
async function cancelSubscriptionAtPeriodEnd(subscriptionId) {
  const subscription = await stripe.subscriptions.update(subscriptionId, {
    cancel_at_period_end: true, // Cancel after current billing cycle
  });
  console.log(`Subscription will cancel at end of period: ${subscriptionId}`);
  return subscription;
}
```

## Updating Subscriptions

### Change Plan/Price

```javascript
async function upgradePlan(subscriptionId, newPriceId) {
  // Retrieve subscription to get current price
  const subscription = await stripe.subscriptions.retrieve(subscriptionId);
  const itemId = subscription.items.data[0].id;

  // Update the price
  const updated = await stripe.subscriptions.update(subscriptionId, {
    items: [
      {
        id: itemId,
        price: newPriceId, // New price
      },
    ],
    // Stripe handles proration automatically:
    // - If upgrading, credit partial refund to next invoice
    // - If downgrading, charge difference on next invoice
    proration_behavior: 'create_prorations', // default
  });

  return updated;
}
```

### Pause Subscription

```javascript
async function pauseSubscription(subscriptionId) {
  const subscription = await stripe.subscriptions.update(subscriptionId, {
    pause_collection: {
      behavior: 'void', // 'void' = skip next invoice, 'mark_uncollectible' = retry later
    },
  });
  return subscription;
}

async function resumeSubscription(subscriptionId) {
  const subscription = await stripe.subscriptions.update(subscriptionId, {
    pause_collection: null, // Clear pause
  });
  return subscription;
}
```

## Usage-Based Billing (Metered)

For charges based on actual usage (API calls, storage, etc.):

### 1. Create Metered Price

```javascript
const price = await stripe.prices.create({
  product: productId,
  currency: 'usd',
  recurring: {
    interval: 'month',
    usage_type: 'metered', // Metered, not flat
    aggregate_usage: 'sum', // Total up usage during period
  },
});
```

### 2. Record Usage

```javascript
async function recordUsage(subscriptionItemId, amount) {
  const usage = await stripe.subscriptionItems.createUsageRecord(
    subscriptionItemId,
    {
      quantity: amount, // Number of API calls, MB of storage, etc.
      timestamp: Math.floor(Date.now() / 1000),
      action: 'increment', // 'increment' or 'set'
    }
  );
  return usage;
}

// Usage in application
// When user makes API call:
await recordUsage(subscriptionItemId, 1);
// Stripe aggregates and bills at end of period
```

## Trials and Promotional Periods

```javascript
async function createSubscriptionWithTrial(customerId, priceId, trialDays = 14) {
  const subscription = await stripe.subscriptions.create({
    customer: customerId,
    items: [{ price: priceId }],
    trial_period_days: trialDays, // Free period
    payment_behavior: 'default_incomplete',
    expand: ['latest_invoice.payment_intent'],
  });

  // Customer has trialDays free, then first charge happens
  return subscription;
}

// Handle trial ending webhook
async function handleTrialWillEnd(subscription) {
  const { customer, trial_end } = subscription;
  
  // Send reminder email before trial ends
  const daysUntilEnd = Math.floor((trial_end * 1000 - Date.now()) / (1000 * 60 * 60 * 24));
  
  if (daysUntilEnd <= 3) {
    await emailService.sendTrialEndingEmail(customer);
  }
}
```

## Dunning (Payment Retry) Flow

Stripe automatically retries failed payments, but you can customize the flow:

```javascript
// Webhook handler for invoice payment failure
async function handleInvoicePaymentFailed(invoice) {
  const { customer, number, amount_due, attempted } = invoice;

  console.log(`Invoice #${number} payment failed (attempt ${attempted})`);

  // Track attempt count
  await db.invoices.update(
    { stripeInvoiceId: invoice.id },
    { paymentAttempts: attempted }
  );

  // Customize email based on attempt
  if (attempted === 1) {
    // First attempt, friendly reminder
    await emailService.sendPaymentFailedEmail(customer, 'Your payment failed. Please retry.');
  } else if (attempted === 2) {
    // Second attempt, urgent
    await emailService.sendPaymentFailedEmail(customer, 'Your subscription is at risk.');
  } else if (attempted >= 3) {
    // Give up on retries
    const subscription = await stripe.subscriptions.retrieve(invoice.subscription);
    await stripe.subscriptions.del(subscription.id);
    await emailService.sendSubscriptionCanceledEmail(customer, 'Failed payments');
  }
}
```

## Customer Portal

Let customers manage subscriptions, payment methods, and view invoices without building UI:

```javascript
async function createPortalSession(customerId, returnUrl) {
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: returnUrl, // URL to return to after portal
    configuration: 'bpc_...', // Optional: configure what customers can do
  });

  return session.url; // Redirect customer here
}

// In frontend
<a href={portalUrl}>Manage Subscription</a>
```

## Billing Email and Invoice Management

### Automatic Invoicing

Stripe automatically creates and sends invoices. Customize in Dashboard > Settings > Billing Settings:

- Email address invoices are sent from
- Invoice prefix (e.g., "INV-" for Invoice-001)
- Invoice days ahead (e.g., send 3 days before due)
- Retry schedule for failed payments

### Custom Invoice Handling

```javascript
// Retrieve subscription invoices
async function getSubscriptionInvoices(subscriptionId) {
  const invoices = await stripe.invoices.list({
    subscription: subscriptionId,
    limit: 12, // Last 12 months
  });

  return invoices.data.map((inv) => ({
    id: inv.id,
    date: new Date(inv.created * 1000),
    amount: inv.amount_paid / 100,
    status: inv.status, // 'draft', 'open', 'paid', 'void', 'uncollectible'
    pdfUrl: inv.invoice_pdf,
  }));
}

// Send custom invoice email
async function sendCustomInvoiceEmail(invoiceId, customerEmail) {
  const invoice = await stripe.invoices.retrieve(invoiceId);
  await emailService.sendInvoice(customerEmail, {
    invoiceNumber: invoice.number,
    pdfUrl: invoice.invoice_pdf,
    amount: invoice.total / 100,
    dueDate: new Date(invoice.due_date * 1000),
  });
}
```

## Testing Subscriptions

```javascript
// Test helpers
const testCardNumbers = {
  success: '4242 4242 4242 4242',
  decline: '4000 0000 0000 0002',
  requiresAuth: '4000 0025 0000 3155',
};

// In Stripe test dashboard: verify subscription appears immediately
// In events logs: watch for customer.subscription.created, invoice.created, charge.succeeded
```
