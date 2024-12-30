// extensions/hooks/auto-seller-role/index.js

export default ({ action }, { services, database }) => {
  action("users.create", async (payload, key, collection) => {
    try {
      const user_id = payload.key;

      if (!user_id) {
        throw new Error("User not found");
      }

      // Seller rolünü database'den bulalım
      const roleResult = await database.raw(
        "SELECT id FROM directus_roles WHERE name = ?",
        ["Seller"]
      );

      // Check if roleResult exists and has rows
      if (!roleResult || !roleResult.rows || roleResult.rows.length === 0) {
        throw new Error("No Seller role found in database");
      }

      const sellerRole = roleResult.rows[0];
      if (!sellerRole || !sellerRole.id) {
        throw new Error("Invalid Seller role structure");
      }

      // Direkt database update kullanalım
      await database.raw("UPDATE directus_users SET role = ? WHERE id = ?", [
        sellerRole.id,
        user_id,
      ]);

	  const mailAddress = payload.payload.email;

      // Kullanıcının subscription_usage kaydı var mı kontrol et
      const usageResult = await database.raw(
        "SELECT id FROM subscription_usage WHERE user_mail = ?",
        [mailAddress]
      );

      // Safely check for existing usage
      if (!usageResult || !usageResult.rows || usageResult.rows.length === 0) {
        console.log("No existing subscription usage found for:", mailAddress);
        // Handle case where no usage exists
      }

      const existingUsage = usageResult.rows[0];
      // Handle existing usage

      // Eğer kayıt yoksa yeni kayıt oluştur
      if (!existingUsage) {
        await database.raw(
          `
				INSERT INTO subscription_usage 
				(user_id, user_mail, store_count, store_creation_count, product_count, review_count, analysis_count, date_created)
				VALUES (?, ?, 0, 0, 0, 0, 0, NOW())
			`,
          [user_id, mailAddress]
        );
      }

      console.log(`Role updated for user: ${mailAddress}`, {
        userId: user_id,
        roleId: sellerRole.id,
        existingUsage: !!existingUsage,
      });
    } catch (error) {
      console.error("Error in auto-seller-role hook:", error);
      console.log("Error details:", {
        message: error.message,
        stack: error.stack,
      });
    }
  });
};
