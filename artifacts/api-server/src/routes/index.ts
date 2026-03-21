import { Router, type IRouter } from "express";
import healthRouter from "./health";
import textbookRouter from "./textbook";

const router: IRouter = Router();

router.use(healthRouter);
router.use(textbookRouter);

export default router;
