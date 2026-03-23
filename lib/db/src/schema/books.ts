import { pgTable, serial, text, boolean, timestamp } from "drizzle-orm/pg-core";

export const booksTable = pgTable("books", {
  id: serial("id").primaryKey(),
  jobId: text("job_id").notNull().unique(),
  title: text("title").notNull(),
  topic: text("topic").notNull(),
  htmlData: text("html_data"),
  pdfData: text("pdf_data"),
  epubData: text("epub_data"),
  approved: boolean("approved").default(false).notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export type Book = typeof booksTable.$inferSelect;
export type InsertBook = typeof booksTable.$inferInsert;
