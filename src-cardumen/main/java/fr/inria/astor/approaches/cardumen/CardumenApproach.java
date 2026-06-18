package fr.inria.astor.approaches.cardumen;

import java.util.List;

import com.martiansoftware.jsap.JSAPException;

import fr.inria.astor.approaches.jgenprog.JGenProg;
import fr.inria.astor.core.entities.ProgramVariant;
import fr.inria.astor.core.manipulation.MutationSupporter;
import fr.inria.astor.core.manipulation.filters.TargetElementProcessor;
import fr.inria.astor.core.setup.ConfigurationProperties;
import fr.inria.astor.core.setup.ProjectRepairFacade;
import fr.inria.astor.core.solutionsearch.spaces.ingredients.scopes.ExpressionClassTypeIngredientSpace;
import fr.inria.astor.core.solutionsearch.spaces.ingredients.scopes.ExpressionTypeIngredientSpace;
import fr.inria.astor.core.solutionsearch.spaces.ingredients.scopes.IngredientPoolScope;
import fr.inria.astor.core.stats.Stats;
import fr.inria.astor.core.stats.Stats.GeneralStatEnum;
import fr.inria.main.ExecutionResult;
import fr.inria.main.evolution.ExtensionPoints;

/**
 * 
 * @author Matias Martinez
 *
 */
public class CardumenApproach extends JGenProg {

	public CardumenApproach(MutationSupporter mutatorExecutor, ProjectRepairFacade projFacade) throws JSAPException {
		super(mutatorExecutor, projFacade);
		// Default configuration of Cardumen:
		ConfigurationProperties.setProperty("cleantemplates", "true");

		if (!ConfigurationProperties.hasProperty(ExtensionPoints.INGREDIENT_TRANSFORM_STRATEGY.identifier)) {

			if (ConfigurationProperties.getPropertyBool("probabilistictransformation")) {
				ConfigurationProperties.setProperty(ExtensionPoints.INGREDIENT_TRANSFORM_STRATEGY.identifier,
						"name-probability-based");
			} else
				ConfigurationProperties.setProperty(ExtensionPoints.INGREDIENT_TRANSFORM_STRATEGY.identifier,
						"random-variable-replacement");
		}

		ConfigurationProperties.setProperty(ExtensionPoints.TARGET_CODE_PROCESSOR.identifier, "expression");
		ConfigurationProperties.setProperty(ExtensionPoints.OPERATORS_SPACE.identifier, "r-expression");
		setPropertyIfNotDefined(ExtensionPoints.INGREDIENT_SEARCH_STRATEGY.identifier, "name-probability-based");

	}

	@Override
	protected void loadIngredientPool() throws JSAPException, Exception {
		List<TargetElementProcessor<?>> ingredientProcessors = this.getTargetElementProcessors();
		ExpressionTypeIngredientSpace ingredientspace = ((ConfigurationProperties.getPropertyBool("uniformreplacement"))
				? new ExpressionClassTypeIngredientSpace(ingredientProcessors)
				: new ExpressionTypeIngredientSpace(ingredientProcessors));
		String scope = ConfigurationProperties.getProperty(ExtensionPoints.INGREDIENT_STRATEGY_SCOPE.identifier);
		if (scope != null) {
			ingredientspace.scope = IngredientPoolScope.valueOf(scope.toUpperCase());
		}
		this.setIngredientPool(ingredientspace);
	}

	/**
	 * Counts every candidate that reaches compile/validation, accumulated across all
	 * modification points. This is the single choke point through which both the normal
	 * Cardumen evolutionary loop and {@link CardumenExportEngine} test a candidate.
	 */
	@Override
	public boolean processCreatedVariant(ProgramVariant programVariant, int generation) throws Exception {
		Stats.currentStat.increment(GeneralStatEnum.NR_TESTED_CANDIDATES);
		return super.processCreatedVariant(programVariant, generation);
	}

	/**
	 * Surfaces the two Cardumen performance measurements at the end of a run: the total
	 * number of candidates tested and the total runtime. Both are also present in the
	 * standard stats output ({@code NR_TESTED_CANDIDATES} and {@code TOTAL_TIME}).
	 */
	@Override
	public ExecutionResult atEnd() {
		ExecutionResult result = super.atEnd();
		Object tested = Stats.currentStat.getGeneralStats().get(GeneralStatEnum.NR_TESTED_CANDIDATES);
		Object time = Stats.currentStat.getGeneralStats().get(GeneralStatEnum.TOTAL_TIME);
		log.info("Cardumen: total candidates tested = " + (tested != null ? tested : 0));
		log.info("Cardumen: total runtime (s) = " + time);
		return result;
	}

}
