const test = require("node:test");
const assert = require("node:assert");
const { ShoppingCart } = require("../src/cart.js");

test("Cart calculates total for standard items", () => {
  const cart = new ShoppingCart();
  cart.addItem("Book", 20, 2);
  assert.strictEqual(cart.getTotal(), 40);
});

test("Cart applies 20% discount on orders of $100 or more with SAVE20 coupon", () => {
  const cart = new ShoppingCart();
  cart.addItem("Headphones", 100, 1);
  cart.applyDiscount("SAVE20");
  
  // With SAVE20, a $100 order should total $80.
  // Because of the bug in cart.js (subtotal > 100 instead of subtotal >= 100), this fails with 100 !== 80!
  assert.strictEqual(cart.getTotal(), 80);
});

