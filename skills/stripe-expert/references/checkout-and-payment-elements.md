# Checkout and Payment Elements

## Stripe Checkout (Hosted Solution)

Stripe Checkout is the easiest path to accept payments: hosted by Stripe, handles payment methods globally, and reduces PCI scope.

### Setup

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
const express = require('express');

app.post('/create-checkout-session', async (req, res) => {
  try {
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card', 'alipay', 'ideal'], // payment methods to accept
      line_items: [
        {
          price_data: {
            currency: 'usd',
            product_data: {
              name: 'Premium Subscription',
              description: '1 year of premium features',
              images: ['https://example.com/product.jpg'],
            },
            unit_amount: 9900, // $99.00 in cents
          },
          quantity: 1,
        },
      ],
      mode: 'payment', // or 'subscription' for recurring charges
      success_url: 'https://example.com/success?session_id={CHECKOUT_SESSION_ID}',
      cancel_url: 'https://example.com/cancel',
      customer: customerId, // associate with existing customer (optional)
      metadata: { orderId: req.body.orderId, userId: req.body.userId },
      billing_address_collection: 'required', // collect billing address
      phone_number_collection: { enabled: true }, // collect phone
    });

    res.json({ sessionId: session.id });
  } catch (error) {
    console.error('Checkout session creation failed:', error);
    res.status(500).json({ error: error.message });
  }
});
```

### Frontend: Redirect to Checkout

```html
<!-- HTML/React -->
<form id="checkout-form">
  <button id="checkout-button">Pay $99.00</button>
</form>

<script src="https://js.stripe.com/v3/"></script>
<script>
  const checkoutButton = document.getElementById('checkout-button');

  checkoutButton.addEventListener('click', async (e) => {
    e.preventDefault();
    const response = await fetch('/create-checkout-session', { method: 'POST' });
    const { sessionId } = await response.json();

    // Redirect to Stripe Checkout
    const stripe = Stripe('pk_test_...'); // public key
    stripe.redirectToCheckout({ sessionId });
  });
</script>
```

## Payment Element (Recommended for Custom Checkout)

Payment Element is embedded in your checkout page; it detects the customer's location and shows relevant payment methods (cards, wallets, bank transfers).

### Setup: Server-Side Intent Creation

```javascript
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

app.post('/create-payment-intent', async (req, res) => {
  try {
    const paymentIntent = await stripe.paymentIntents.create({
      amount: req.body.amount, // in cents
      currency: 'usd',
      payment_method_types: ['card', 'alipay', 'ideal'],
      metadata: { orderId: req.body.orderId },
    });

    res.json({
      clientSecret: paymentIntent.client_secret,
      publishableKey: process.env.STRIPE_PUBLIC_KEY,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});
```

### Setup: Frontend Integration (React)

```jsx
import React, { useState, useEffect } from 'react';
import {
  EmbeddedCheckoutProvider,
  EmbeddedCheckout,
} from '@stripe/react-stripe-js';
import { loadStripe } from '@stripe/js';

const StripeCheckout = ({ orderId, amount }) => {
  const [clientSecret, setClientSecret] = useState('');
  const stripe = loadStripe('pk_test_...');

  useEffect(() => {
    // Fetch client secret from server
    fetch('/create-payment-intent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount, orderId }),
    })
      .then((res) => res.json())
      .then((data) => setClientSecret(data.clientSecret));
  }, [amount, orderId]);

  return clientSecret ? (
    <EmbeddedCheckoutProvider stripe={stripe} options={{ clientSecret }}>
      <EmbeddedCheckout />
    </EmbeddedCheckoutProvider>
  ) : (
    <p>Loading...</p>
  );
};

export default StripeCheckout;
```

## Custom Payment Form with Stripe Elements

Use Stripe Elements for full control over form design and UX.

### HTML Setup

```html
<form id="payment-form">
  <div id="card-element"></div>
  <div id="card-errors" role="alert"></div>
  <button type="submit" id="submit-button">Pay</button>
</form>

<script src="https://js.stripe.com/v3/"></script>
<script>
  const stripe = Stripe('pk_test_...');
  const elements = stripe.elements();
  const cardElement = elements.create('card');
  cardElement.mount('#card-element');

  const form = document.getElementById('payment-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Create PaymentMethod
    const { error, paymentMethod } = await stripe.createPaymentMethod({
      type: 'card',
      card: cardElement,
    });

    if (error) {
      document.getElementById('card-errors').textContent = error.message;
    } else {
      // Send paymentMethod.id to server
      fetch('/confirm-payment', {
        method: 'POST',
        body: JSON.stringify({
          paymentMethodId: paymentMethod.id,
          amount: 9900,
        }),
        headers: { 'Content-Type': 'application/json' },
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.status === 'succeeded') {
            alert('Payment successful!');
          } else {
            alert('Payment failed.');
          }
        });
    }
  });
</script>
```

### Server-Side Confirmation

```javascript
app.post('/confirm-payment', async (req, res) => {
  const { paymentMethodId, amount } = req.body;

  try {
    const paymentIntent = await stripe.paymentIntents.create({
      amount,
      currency: 'usd',
      payment_method: paymentMethodId,
      confirm: true, // Confirm and charge immediately
      return_url: 'https://example.com/return',
    });

    if (paymentIntent.status === 'succeeded') {
      res.json({ status: 'succeeded', intent: paymentIntent.id });
    } else if (paymentIntent.status === 'requires_action') {
      // Customer authentication required (3D Secure)
      res.json({
        status: 'action_required',
        clientSecret: paymentIntent.client_secret,
      });
    }
  } catch (error) {
    res.status(402).json({ error: error.message });
  }
});
```

## Key Decisions

| Scenario | Recommendation |
|---|---|
| Simple product purchase, minimal customization | Stripe Checkout (hosted) |
| Custom checkout design, need full control | Payment Element (embedded) |
| Complex form with multiple steps or flows | Custom Elements |
| Subscription or recurring billing | Checkout (mode: 'subscription') or Billing Portal |
| Mobile app | Stripe SDK for iOS/Android or Payment Sheet |

## Redirect and Confirmation Flows

After Payment Element or Checkout, always confirm the payment status server-side before marking order as paid:

```javascript
// Server: fetch intent status after redirect
app.get('/confirm-payment-status/:intentId', async (req, res) => {
  try {
    const intent = await stripe.paymentIntents.retrieve(req.params.intentId);
    
    if (intent.status === 'succeeded') {
      // Mark order as paid
      res.json({ status: 'paid' });
    } else if (intent.status === 'processing') {
      res.json({ status: 'processing' });
    } else {
      res.json({ status: 'failed' });
    }
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});
```
