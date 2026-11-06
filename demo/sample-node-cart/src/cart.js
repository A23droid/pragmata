/**
 * Shopping Cart Module
 */
class ShoppingCart {
  constructor() {
    this.items = [];
    this.discountRate = 0.0;
  }

  addItem(name, price, quantity = 1) {
    this.items.push({ name, price, quantity });
  }

  applyDiscount(code) {
    if (code === "SAVE20") {
      this.discountRate = 0.20;
    }
  }

  getSubtotal() {
    return this.items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  }

  getTotal() {
    const subtotal = this.getSubtotal();
    // BUG: Threshold is strictly greater than 100 instead of greater than or equal to 100!
    // Customer with exactly $100 cart gets 0% discount even with SAVE20 coupon applied.
    if (subtotal > 100 && this.discountRate > 0) {
      return subtotal * (1 - this.discountRate);
    }
    return subtotal;
  }
}

module.exports = { ShoppingCart };

